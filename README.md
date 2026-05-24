# async-jobs

FastAPI + Celery + Redis job-processing service. Submit a job, poll for status, or stream state changes over SSE. State is persisted in Postgres.

## What it does

- `POST /jobs` — enqueue a job; returns a job ID immediately
- `GET /jobs/{id}` — poll the current state and result
- `GET /jobs/{id}/stream` — receive state-change events over SSE
- `GET /healthz` — probe Postgres and Redis connectivity
- `GET /metrics` — Prometheus exposition

Jobs move through a state machine: `queued → running → done | failed`.

The Celery worker retries failed tasks with exponential backoff (up to 3 retries, max 60s delay). After exhausting retries the job transitions to `failed` and the error is stored.

Idempotency keys prevent duplicate submissions. Pass `Idempotency-Key: <your-key>` on `POST /jobs`; a second request with the same key returns the existing job without dispatching another task.

## Architecture

```
Client
  │
  │  POST /jobs
  ▼
FastAPI API
  │  writes job (state=queued) to Postgres
  │  enqueues task to Redis (Celery broker)
  │
  ├──► Postgres (job state store)
  │
  └──► Redis (broker + result backend)
         │
         ▼
     Celery Worker
         │  reads task from queue
         │  updates job → running in Postgres
         │  executes payload
         │  updates job → done | failed in Postgres
         │  (retries on failure, exponential backoff)
```

### Request sequence — submit and poll

```
Client          FastAPI         Postgres          Redis          Worker
  │                │               │                │               │
  │  POST /jobs    │               │                │               │
  │───────────────►│               │                │               │
  │                │  INSERT job   │                │               │
  │                │──────────────►│                │               │
  │                │  task.delay() │                │               │
  │                │───────────────────────────────►│               │
  │  202 {id, queued}              │                │               │
  │◄───────────────│               │                │               │
  │                │               │                │  consume task │
  │                │               │                │──────────────►│
  │                │               │  UPDATE running│               │
  │                │               │◄───────────────────────────────│
  │                │               │  UPDATE done   │               │
  │                │               │◄───────────────────────────────│
  │  GET /jobs/{id}│               │                │               │
  │───────────────►│               │                │               │
  │                │  SELECT job   │                │               │
  │                │──────────────►│                │               │
  │  200 {done, result}            │                │               │
  │◄───────────────│               │                │               │
```

### Retry sequence — task failure

```
Worker          Postgres         Redis
  │                │               │
  │  UPDATE running│               │
  │───────────────►│               │
  │  execute (fails)               │
  │  UPDATE retry_count            │
  │───────────────►│               │
  │  re-queue (backoff)            │
  │───────────────────────────────►│
  │    ... (up to max_retries) ... │
  │  UPDATE failed │               │
  │───────────────►│               │
```

## Run locally

Requires Docker and Docker Compose.

```bash
docker compose up --build
```

This starts Postgres, Redis, runs Alembic migrations, then starts the API and worker.

- API: http://localhost:8000
- OpenAPI docs: http://localhost:8000/docs
- Metrics: http://localhost:8000/metrics

## Run without Docker

```bash
# Install dependencies
pip install -e ".[dev]"

# Start Postgres and Redis (e.g. via Docker)
docker compose up postgres redis -d

# Run migrations
alembic upgrade head

# Start API
uvicorn app.main:app --reload

# Start worker (separate terminal)
celery -A app.worker.celery_app worker --loglevel=info --queues=default
```

Copy `.env.example` to `.env` and adjust `DATABASE_URL` and `REDIS_URL` if needed.

## Test

```bash
pytest
```

Tests run against SQLite in-memory. No external services needed.

```bash
pytest -v                  # verbose
pytest tests/test_retry.py # single module
```

## Deploy to Fly.io

```bash
# Create app (one-time)
fly launch --no-deploy

# Add managed Postgres
fly postgres create
fly postgres attach <pg-app-name>

# Add Redis (Upstash or fly-redis)
fly ext redis create

# Set secrets
fly secrets set REDIS_URL=<upstash-url> CELERY_RESULT_BACKEND=<upstash-url>/1

# Deploy
fly deploy

# Run migrations after deploy
fly ssh console -C "alembic upgrade head"

# Scale worker process
fly scale count worker=2
```

The `fly.toml` configures `/healthz` as the health check path.

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql://...@localhost/asyncjobs` | Postgres connection string |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis broker URL |
| `CELERY_RESULT_BACKEND` | `redis://localhost:6379/1` | Celery result backend URL |
| `TASK_MAX_RETRIES` | `3` | Max retry attempts per task |
| `TASK_RETRY_BACKOFF` | `2` | Base retry delay in seconds |
| `DEBUG` | `false` | Enable debug mode and pretty logs |
| `LOG_LEVEL` | `INFO` | Logging level |

## Project structure

```
app/
  api/
    health.py    — /healthz
    jobs.py      — POST /jobs, GET /jobs/{id}
    stream.py    — GET /jobs/{id}/stream (SSE)
  worker/
    celery_app.py — Celery instance and config
    tasks.py      — process_job task, retry/failure logic
  config.py      — pydantic-settings
  database.py    — SQLAlchemy engine and session
  logging_config.py — structlog setup and request ID middleware
  main.py        — FastAPI app, middleware, router wiring
  metrics.py     — Prometheus counters and histograms
  models.py      — Job ORM model and state machine
  schemas.py     — Pydantic request/response schemas
alembic/
  versions/0001_create_jobs_table.py
tests/
  conftest.py
  test_idempotency.py
  test_retry.py
  test_state_transitions.py
```
