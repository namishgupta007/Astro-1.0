"""Configuration settings for Astral Cartographer backend."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


class Settings:
    """Application settings loaded from environment variables with safe defaults."""

    def __init__(self) -> None:
        # Base Data Directory
        raw_data_dir = os.environ.get("ASTRAL_DATA_DIR", "data")
        self.data_dir: Path = Path(raw_data_dir).resolve()

        # Ingestion and Archive Limits
        self.max_archive_mb: int = int(os.environ.get("ASTRAL_MAX_ARCHIVE_MB", "100"))
        self.max_extracted_mb: int = int(os.environ.get("ASTRAL_MAX_EXTRACTED_MB", "500"))
        self.max_files: int = int(os.environ.get("ASTRAL_MAX_FILES", "20000"))
        self.max_single_file_mb: int = int(
            os.environ.get("ASTRAL_MAX_SINGLE_FILE_MB", "20")
        )

        # Source File Response Limits
        self.max_source_response_mb: int = int(
            os.environ.get("ASTRAL_MAX_SOURCE_RESPONSE_MB", "1")
        )

        # Concurrency Limits
        self.max_concurrent_jobs: int = int(
            os.environ.get("ASTRAL_MAX_CONCURRENT_JOBS", "2")
        )

        # CORS Allowed Origins
        raw_cors = os.environ.get(
            "ASTRAL_CORS_ORIGINS",
            "http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000,http://127.0.0.1:5173",
        )
        self.cors_origins: list[str] = [
            origin.strip() for origin in raw_cors.split(",") if origin.strip()
        ]

        # Server Host and Port
        self.host: str = os.environ.get("ASTRAL_HOST", "127.0.0.1")
        self.port: int = int(os.environ.get("ASTRAL_PORT", "8000"))

    @property
    def db_path(self) -> Path:
        """Absolute path to the SQLite database file."""
        return self.data_dir / "astral.db"

    @property
    def repositories_dir(self) -> Path:
        """Absolute path to the directory storing repository workspaces."""
        return self.data_dir / "repositories"

    def get_repo_dir(self, repo_id: str) -> Path:
        """Return the root directory for a specific indexed repository."""
        return self.repositories_dir / repo_id

    def get_repo_source_dir(self, repo_id: str) -> Path:
        """Return the extracted source directory for a specific repository."""
        return self.get_repo_dir(repo_id) / "source"

    def get_repo_artifact_dir(self, repo_id: str) -> Path:
        """Return the artifacts directory for a specific repository."""
        return self.get_repo_dir(repo_id) / "artifacts"

    def ensure_directories(self) -> None:
        """Ensure all required base directories exist."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.repositories_dir.mkdir(parents=True, exist_ok=True)


# Global settings singleton
settings = Settings()
