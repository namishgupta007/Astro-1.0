"""Repository-scoped cluster exploration and AI architectural summarization service."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from app.api.schemas import (
    ClusterDetailItem,
    ClusterNodeDetail,
    ClusterSummarizeResponse,
    RepositoryClustersResponse,
)
from app.config import settings
from app.services.ai_client import ai_client
from app.services.graph_analytics_service import graph_analytics_service
from app.storage.repository_store import get_repository

logger = logging.getLogger(__name__)


class ClusterService:
    """Manages Louvain community cluster profiles, persistence, and architectural summaries."""

    def _get_summaries_file(self, repo_id: str) -> Path:
        """Return the path to the persisted cluster summaries JSON file."""
        return settings.get_repo_artifact_dir(repo_id) / "cluster_summaries.json"

    def _load_cached_summaries(self, repo_id: str) -> dict[str, str]:
        """Load cached cluster summaries from disk if present."""
        path = self._get_summaries_file(repo_id)
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as exc:
                logger.warning("Failed to load cluster summaries for %s: %s", repo_id, exc)
        return {}

    def _save_cached_summaries(self, repo_id: str, summaries: dict[str, str]) -> None:
        """Persist cluster summaries to disk."""
        path = self._get_summaries_file(repo_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(summaries, f, indent=2)

    def get_repository_clusters(
        self,
        repo_id: str,
        target_cluster_id: Optional[int] = None,
    ) -> RepositoryClustersResponse:
        """Retrieve all detected community clusters with top central nodes and summaries."""
        repo = get_repository(repo_id)
        if not repo:
            raise FileNotFoundError(f"Repository '{repo_id}' not found")

        if repo.status != "completed":
            raise ValueError(f"Repository indexing is in '{repo.status}' state; clusters not ready")

        analytics = graph_analytics_service.get_repository_analytics(repo_id)
        cached_summaries = self._load_cached_summaries(repo_id)

        # Group nodes by cluster_id
        cluster_nodes: dict[int, list[dict[str, Any]]] = {}
        for n in analytics.get("nodes", []):
            cid = n.get("cluster_id", 0)
            cluster_nodes.setdefault(cid, []).append(n)

        # If target_cluster_id specified, ensure it exists
        if target_cluster_id is not None and target_cluster_id not in cluster_nodes:
            raise FileNotFoundError(
                f"Cluster {target_cluster_id} not found in repository '{repo_id}'"
            )

        clusters_result: list[ClusterDetailItem] = []
        for cid in sorted(cluster_nodes.keys()):
            if target_cluster_id is not None and cid != target_cluster_id:
                continue

            nodes = cluster_nodes[cid]
            # Rank descending by normalized centrality
            nodes_sorted = sorted(
                nodes,
                key=lambda x: x.get("metrics", {}).get("normalized_centrality", 0.0),
                reverse=True,
            )

            # Extract languages and primary directory paths
            languages: set[str] = set()
            directories: set[str] = set()
            top_node_details: list[ClusterNodeDetail] = []
            node_ids: list[str] = []

            for n in nodes_sorted:
                node_ids.append(n["id"])
                path = n.get("path", "")
                if "/" in path:
                    directories.add(path.split("/")[0])
                elif path:
                    directories.add(path)

            for n in nodes_sorted[:5]:
                top_node_details.append(
                    ClusterNodeDetail(
                        id=n["id"],
                        label=n.get("label", n["id"]),
                        type=n.get("type", "unknown"),
                        path=n.get("path", ""),
                        centrality=n.get("metrics", {}).get("normalized_centrality", 0.0),
                    )
                )

            summary_text = cached_summaries.get(str(cid))

            clusters_result.append(
                ClusterDetailItem(
                    cluster_id=cid,
                    node_count=len(nodes),
                    summary=summary_text,
                    languages=sorted(languages),
                    primary_directories=sorted(directories)[:5],
                    top_nodes=top_node_details,
                    node_ids=node_ids,
                )
            )

        return RepositoryClustersResponse(
            repository_id=repo_id,
            total_clusters=len(clusters_result),
            clusters=clusters_result,
        )

    async def summarize_repository_clusters(
        self,
        repo_id: str,
        cluster_id: Optional[int] = None,
        force_refresh: bool = False,
    ) -> ClusterSummarizeResponse:
        """Synthesize and cache high-level architectural summaries for galaxy clusters."""
        clusters_resp = self.get_repository_clusters(repo_id, target_cluster_id=cluster_id)
        cached_summaries = self._load_cached_summaries(repo_id)

        generated_count = 0
        cached_count = 0
        summaries: dict[str, str] = dict(cached_summaries)

        for cluster in clusters_resp.clusters:
            cid_str = str(cluster.cluster_id)

            if not force_refresh and cid_str in cached_summaries and cached_summaries[cid_str]:
                summaries[cid_str] = cached_summaries[cid_str]
                cached_count += 1
                continue

            # Generate summary via AI client
            top_nodes_data = [n.model_dump() for n in cluster.top_nodes]
            summary_text = await ai_client.generate_cluster_summary(
                cluster_id=cluster.cluster_id,
                top_nodes=top_nodes_data,
                languages=cluster.languages,
                paths=cluster.primary_directories,
            )

            summaries[cid_str] = summary_text
            generated_count += 1

        self._save_cached_summaries(repo_id, summaries)

        return ClusterSummarizeResponse(
            repository_id=repo_id,
            total_clusters=len(clusters_resp.clusters),
            summaries={str(c.cluster_id): summaries[str(c.cluster_id)] for c in clusters_resp.clusters},
            generated_count=generated_count,
            cached_count=cached_count,
        )


# Global cluster service singleton
cluster_service = ClusterService()
