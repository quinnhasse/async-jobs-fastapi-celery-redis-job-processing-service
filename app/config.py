from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    database_url: str = "postgresql://postgres:postgres@localhost:5432/asyncjobs"

    # Redis / Celery broker
    redis_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    # Worker
    task_max_retries: int = 3
    task_retry_backoff: int = 2  # seconds, doubled each retry

    # App
    debug: bool = False
    log_level: str = "INFO"


settings = Settings()
