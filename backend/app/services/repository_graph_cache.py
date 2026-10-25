"""Thread-safe LRU cache for repository code graphs and NetworkX topologies.

Guarantees repository-scoped isolation, fast in-memory AI reasoning, and proper
cache invalidation upon reindexing.
"""

from __future__ import annotations

from collections import OrderedDict
import logging
from threading import Lock
from typing import Any, Optional

import networkx as nx

from app.graph.models import CodeGraph

logger = logging.getLogger(__name__)


class RepositoryGraphCache:
    """Thread-safe, bounded LRU cache for repository graph structures."""

    def __init__(self, max_size: int = 10) -> None:
        self.max_size = max_size
        self._cache: OrderedDict[str, tuple[dict[str, Any], nx.DiGraph]] = OrderedDict()
        self._lock = Lock()

    def get(self, repo_id: str) -> Optional[tuple[dict[str, Any], nx.DiGraph]]:
        """Retrieve cached (graph_data, nx_graph) for a specific repository."""
        with self._lock:
            if repo_id not in self._cache:
                return None
            # Move to end for LRU
            self._cache.move_to_end(repo_id)
            return self._cache[repo_id]

    def put(
        self,
        repo_id: str,
        graph_data: dict[str, Any],
        nx_graph: nx.DiGraph,
    ) -> None:
        """Store (graph_data, nx_graph) for a specific repository, evicting oldest if full."""
        with self._lock:
            if repo_id in self._cache:
                self._cache.move_to_end(repo_id)
            self._cache[repo_id] = (graph_data, nx_graph)
            if len(self._cache) > self.max_size:
                evicted_id, _ = self._cache.popitem(last=False)
                logger.debug("Evicted repository graph cache for: %s", evicted_id)

    def invalidate(self, repo_id: str) -> None:
        """Evict a specific repository's cached graph upon reindexing or mutation."""
        with self._lock:
            if repo_id in self._cache:
                del self._cache[repo_id]
                logger.debug("Invalidated graph cache for repository: %s", repo_id)

    def clear(self) -> None:
        """Clear all cached repository graphs."""
        with self._lock:
            self._cache.clear()


# Global cache singleton
repository_graph_cache = RepositoryGraphCache()
