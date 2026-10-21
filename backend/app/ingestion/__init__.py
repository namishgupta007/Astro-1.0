"""Astral Cartographer ingestion package."""

from typing import Any


def __getattr__(name: str) -> Any:
    if name == "scan_repository":
        from app.ingestion.scanner import scan_repository

        return scan_repository
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["scan_repository"]
