import os
from pathlib import Path


class Settings:
    """Read from the environment at access time so tests can override it."""

    @property
    def database_url(self) -> str:
        return os.environ.get("DATABASE_URL", "sqlite:///./gnss.db")

    @property
    def storage_dir(self) -> Path:
        return Path(os.environ.get("STORAGE_DIR", "./storage"))

    @property
    def redis_url(self) -> str:
        return os.environ.get("REDIS_URL", "redis://localhost:6379/0")

    @property
    def job_timeout_seconds(self) -> int:
        return int(os.environ.get("JOB_TIMEOUT_SECONDS", "600"))

    @property
    def max_upload_bytes(self) -> int:
        return int(os.environ.get("MAX_UPLOAD_MB", "50")) * 1024 * 1024


settings = Settings()
