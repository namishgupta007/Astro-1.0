"""Pydantic request and response schemas for Astral Cartographer API."""

from __future__ import annotations

import re
from typing import Any, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator


class HealthResponse(BaseModel):
    """Health endpoint response model."""

    status: str = "ok"
    version: str = "1.0.0"
    database: str = "connected"


class RepositorySubmitRequest(BaseModel):
    """Request model for submitting a public GitHub repository."""

    url: str = Field(
        ...,
        description="Public GitHub repository HTTPS URL (e.g. https://github.com/owner/repo)",
        examples=["https://github.com/pallets/flask"],
    )
    branch: str = Field(
        default="main",
        description="Target branch name to index (default: main)",
        examples=["main"],
    )

    @field_validator("url")
    @classmethod
    def validate_github_url(cls, v: str) -> str:
        trimmed = v.strip()
        parsed = urlparse(trimmed)

        if parsed.scheme != "https":
            raise ValueError("Only HTTPS URLs are supported")

        if parsed.netloc.lower() != "github.com":
            raise ValueError("Only repositories hosted on github.com are supported")

        if parsed.username or parsed.password:
            raise ValueError("Credentials in URL are strictly prohibited")

        # Path should be /owner/repo or /owner/repo.git
        clean_path = parsed.path.strip("/")
        if clean_path.endswith(".git"):
            clean_path = clean_path[:-4]

        segments = [s for s in clean_path.split("/") if s]
        if len(segments) != 2:
            raise ValueError(
                "Invalid repository URL format. Expected 'https://github.com/owner/repository'"
            )

        owner, repo = segments
        valid_name = re.compile(r"^[a-zA-Z0-9_.-]+$")
        if not valid_name.match(owner) or not valid_name.match(repo):
            raise ValueError("Repository owner or name contains invalid characters")

        if ".." in owner or ".." in repo:
            raise ValueError("Path traversal sequences are prohibited")

        return f"https://github.com/{owner}/{repo}"

    @field_validator("branch")
    @classmethod
    def validate_branch(cls, v: str) -> str:
        trimmed = v.strip()
        if not trimmed:
            return "main"
        if ".." in trimmed or "\\" in trimmed or "@" in trimmed or "~" in trimmed or "^" in trimmed or ":" in trimmed or " " in trimmed:
            raise ValueError("Branch name contains forbidden characters")
        if trimmed.startswith("/") or trimmed.endswith("/") or "//" in trimmed:
            raise ValueError("Branch name cannot start/end with slash or contain consecutive slashes")
        if any(ord(c) < 32 or ord(c) == 127 for c in trimmed):
            raise ValueError("Branch name contains control characters")
        return trimmed


class RepositorySubmitResponse(BaseModel):
    """Response returned upon successful acceptance of an indexing request."""

    repository_id: str
    job_id: str
    status: str
    message: str


class RepositorySummary(BaseModel):
    """Summary representation of an indexed repository."""

    id: str
    url: str
    owner: str
    name: str
    branch: str
    status: str
    current_job_id: Optional[str] = None
    created_at: str
    updated_at: str


class RepositoryDetail(RepositorySummary):
    """Detailed metadata for an indexed repository."""

    workspace_dir: str
    artifact_dir: str
    error_message: Optional[str] = None


class RepositoryListResponse(BaseModel):
    """Paginated list of repositories."""

    items: list[RepositorySummary]
    total: int
    limit: int
    offset: int


class JobDetail(BaseModel):
    """Detailed status of an asynchronous indexing job."""

    id: str
    repository_id: str
    status: str
    stage: str
    progress: int
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error_message: Optional[str] = None


class FileItem(BaseModel):
    """Single file record from the scanner inventory."""

    path: str
    size_bytes: int
    sha256: Optional[str] = None
    language: Optional[str] = None
    extension: Optional[str] = None


class FileListResponse(BaseModel):
    """List of indexed files in a repository."""

    repository_id: str
    total_files: int
    files: list[FileItem]


class SourceFileResponse(BaseModel):
    """Source file contents with line metadata."""

    repository_id: str
    path: str
    total_lines: int
    start_line: int
    end_line: int
    content: str
    truncated: bool = False


class SymbolItem(BaseModel):
    """Extracted code symbol representation."""

    id: str
    name: str
    qualified_name: str
    kind: str
    language: str
    file_path: str
    lineno: int
    end_lineno: int
    parent_scope: Optional[str] = None
    signature: Optional[str] = None


class SymbolSearchResponse(BaseModel):
    """Symbol search results."""

    repository_id: str
    query: str
    total_matches: int
    symbols: list[SymbolItem]


class GraphNodeItem(BaseModel):
    """Vertex in the code graph."""

    id: str
    type: str
    name: str
    label: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class GraphEdgeItem(BaseModel):
    """Directed edge in the code graph."""

    id: str
    source: str
    target: str
    type: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class GraphSummaryItem(BaseModel):
    """Aggregate statistics for a code graph."""

    node_count: int
    edge_count: int
    nodes_by_type: dict[str, int] = Field(default_factory=dict)
    edges_by_type: dict[str, int] = Field(default_factory=dict)
    resolved_calls: int = 0
    ambiguous_calls: int = 0
    unresolved_calls: int = 0
    resolved_imports: int = 0
    unresolved_imports: int = 0


class GraphResponse(BaseModel):
    """Complete code graph data."""

    repository_id: str
    schema_version: int
    summary: GraphSummaryItem
    nodes: list[GraphNodeItem]
    edges: list[GraphEdgeItem]
    unresolved_references: list[dict[str, Any]] = Field(default_factory=list)


class DependenciesResponse(BaseModel):
    """Dependencies or callers response for a specific symbol."""

    repository_id: str
    symbol_id: str
    direction: str
    depth: int
    nodes: list[GraphNodeItem]
    edges: list[GraphEdgeItem]


class ImpactAnalysisResponse(BaseModel):
    """Impact analysis traversal report for a symbol."""

    repository_id: str
    target_symbol_id: str
    max_depth: int
    depth_reached: int
    target_node: Optional[GraphNodeItem] = None
    impacted_nodes: list[GraphNodeItem] = Field(default_factory=list)
    impacted_edges: list[GraphEdgeItem] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    """Standardized API error response."""

    detail: str
    code: Optional[str] = None
