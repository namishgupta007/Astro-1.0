"""Database connection and lifecycle management for Astral Cartographer."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sqlite3
from typing import Generator, Optional

from app.config import settings


def get_db_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Create a new SQLite connection with appropriate pragmas."""
    target_path = db_path or settings.db_path
    target_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(
        str(target_path),
        timeout=30.0,
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    # WAL journal mode for safe concurrency
    try:
        conn.execute("PRAGMA journal_mode = WAL;")
    except sqlite3.OperationalError:
        pass
    return conn


@contextmanager
def get_db(db_path: Optional[Path] = None) -> Generator[sqlite3.Connection, None, None]:
    """Context manager providing a transactional SQLite connection."""
    conn = get_db_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: Optional[Path] = None) -> None:
    """Initialize database tables and indexes."""
    with get_db(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS repositories (
                id TEXT PRIMARY KEY,
                url TEXT NOT NULL,
                owner TEXT NOT NULL,
                name TEXT NOT NULL,
                branch TEXT NOT NULL,
                status TEXT NOT NULL,
                current_job_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                workspace_dir TEXT NOT NULL,
                artifact_dir TEXT NOT NULL,
                error_message TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_repositories_url ON repositories(url);

            CREATE TABLE IF NOT EXISTS indexing_jobs (
                id TEXT PRIMARY KEY,
                repository_id TEXT NOT NULL,
                status TEXT NOT NULL,
                stage TEXT NOT NULL,
                progress INTEGER NOT NULL,
                started_at TEXT,
                completed_at TEXT,
                error_message TEXT,
                FOREIGN KEY (repository_id) REFERENCES repositories(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_jobs_repository_id ON indexing_jobs(repository_id);
            CREATE INDEX IF NOT EXISTS idx_jobs_status ON indexing_jobs(status);
            """
        )
