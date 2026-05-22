FROM python:3.12-slim

WORKDIR /app

# Install uv for fast dependency installs
RUN pip install --no-cache-dir uv

COPY pyproject.toml ./
RUN uv pip install --system --no-cache -e .

COPY . .

# Default: run the API server
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
