"""Asynchronous indexing job orchestration service."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import logging
import os
from pathlib import Path
import shutil
import tempfile
from typing import Optional

from app.config import settings
from app.graph.graph_builder import build_graph
from app.ingestion.scanner import scan_repository
from app.parsers.javascript_parser import parse_js_repository_inventory
from app.parsers.python_parser import parse_repository_inventory as parse_py_inventory
from app.services.archive_extractor import extract_archive_safely
from app.services.downloader import download_github_archive
from app.storage.repository_store import update_job, update_repository_status

logger = logging.getLogger(__name__)


class IndexingService:
    """Manages background indexing job execution using a bounded thread pool."""

    def __init__(self, max_workers: Optional[int] = None) -> None:
        workers = max_workers or settings.max_concurrent_jobs
        self.executor = ThreadPoolExecutor(
            max_workers=workers,
            thread_name_prefix="astral-indexer",
        )

    def submit_job(
        self,
        repo_id: str,
        job_id: str,
        url: str,
        branch: str,
    ) -> None:
        """Schedule a background indexing task."""
        self.executor.submit(
            self._execute_indexing_pipeline,
            repo_id,
            job_id,
            url,
            branch,
        )

    def _execute_indexing_pipeline(
        self,
        repo_id: str,
        job_id: str,
        url: str,
        branch: str,
    ) -> None:
        """Run the complete multi-stage analysis pipeline."""
        source_dir = settings.get_repo_source_dir(repo_id)
        artifact_dir = settings.get_repo_artifact_dir(repo_id)

        source_dir.mkdir(parents=True, exist_ok=True)
        artifact_dir.mkdir(parents=True, exist_ok=True)

        inventory_file = artifact_dir / "repository_inventory.json"
        py_analysis_file = artifact_dir / "python_analysis.json"
        js_analysis_file = artifact_dir / "javascript_analysis.json"
        code_graph_file = artifact_dir / "code_graph.json"

        temp_zip_file: Optional[Path] = None

        try:
            logger.info("Starting indexing job %s for repo %s", job_id, repo_id)
            update_job(job_id, status="running", started=True)
            update_repository_status(repo_id, status="running")

            # ----------------------------------------------------
            # Stage A: Downloading
            # ----------------------------------------------------
            update_job(job_id, stage="downloading", progress=10)
            temp_fd, temp_zip_str = tempfile.mkstemp(suffix=".zip", prefix="astral_dl_")
            os.close(temp_fd)
            temp_zip_file = Path(temp_zip_str)

            download_github_archive(
                url=url,
                branch=branch,
                dest_path=temp_zip_file,
            )

            # ----------------------------------------------------
            # Stage B: Extracting
            # ----------------------------------------------------
            update_job(job_id, stage="extracting", progress=25)
            # Clear any preexisting source files
            shutil.rmtree(source_dir, ignore_errors=True)
            source_dir.mkdir(parents=True, exist_ok=True)

            extract_archive_safely(
                zip_path=temp_zip_file,
                target_source_dir=source_dir,
            )

            # Delete temporary archive download promptly
            if temp_zip_file and temp_zip_file.exists():
                temp_zip_file.unlink(missing_ok=True)
                temp_zip_file = None

            # ----------------------------------------------------
            # Stage C: Scanning
            # ----------------------------------------------------
            update_job(job_id, stage="scanning", progress=40)
            scan_repository(
                repository_path=source_dir,
                output_path=inventory_file,
            )

            # ----------------------------------------------------
            # Stage D: Parsing Python code
            # ----------------------------------------------------
            update_job(job_id, stage="parsing_python", progress=60)
            parse_py_inventory(
                inventory_path=inventory_file,
                repo_root=source_dir,
                output_path=py_analysis_file,
            )

            # ----------------------------------------------------
            # Stage E: Parsing JavaScript and TypeScript code
            # ----------------------------------------------------
            update_job(job_id, stage="parsing_javascript", progress=75)
            parse_js_repository_inventory(
                inventory_path=inventory_file,
                repo_root=source_dir,
                output_path=js_analysis_file,
            )

            # ----------------------------------------------------
            # Stage F: Building unified graph
            # ----------------------------------------------------
            update_job(job_id, stage="building_graph", progress=90)
            build_graph(
                repo_root=source_dir,
                inventory_path=inventory_file,
                analysis_path=[py_analysis_file, js_analysis_file],
                output_path=code_graph_file,
            )

            # ----------------------------------------------------
            # Stage G: Validating and saving results
            # ----------------------------------------------------
            update_job(job_id, stage="saving_results", progress=98)
            for path, name in [
                (inventory_file, "repository inventory"),
                (py_analysis_file, "Python analysis"),
                (js_analysis_file, "JavaScript analysis"),
                (code_graph_file, "code graph"),
            ]:
                if not path.exists():
                    raise RuntimeError(f"Expected artifact '{name}' was not created at {path}")
                # Verify JSON format
                with open(path, "r", encoding="utf-8") as f:
                    json.load(f)

            # Mark completed
            update_job(
                job_id,
                status="completed",
                stage="completed",
                progress=100,
                completed=True,
            )
            update_repository_status(repo_id, status="completed")
            logger.info("Indexing job %s for repo %s completed successfully", job_id, repo_id)

        except Exception as err:
            logger.exception("Indexing job %s failed: %s", job_id, err)
            err_msg = str(err)
            update_job(
                job_id,
                status="failed",
                stage="failed",
                error_message=err_msg,
                completed=True,
            )
            update_repository_status(
                repo_id,
                status="failed",
                error_message=err_msg,
            )
        finally:
            if temp_zip_file and temp_zip_file.exists():
                temp_zip_file.unlink(missing_ok=True)

    def shutdown(self, wait: bool = False) -> None:
        """Shut down the thread pool."""
        self.executor.shutdown(wait=wait)


# Global indexing service singleton
indexing_service = IndexingService()
