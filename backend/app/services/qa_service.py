"""Repository-scoped codebase Q&A service grounded in static graph topology and source context."""

from __future__ import annotations

import json
import logging
from pathlib import Path
import re
import time
from typing import Any, Optional

import networkx as nx

from app.api.schemas import QAResponse
from app.config import settings
from app.services.ai_client import ai_client
from app.services.graph_analytics_service import build_networkx_graph, graph_analytics_service
from app.services.repository_graph_cache import repository_graph_cache
from app.storage.repository_store import get_repository

logger = logging.getLogger(__name__)

STOP_WORDS: frozenset[str] = frozenset(
    {
        "a", "an", "the", "and", "or", "in", "on", "at", "to", "for", "of", "with",
        "by", "is", "are", "was", "were", "be", "been", "how", "what", "where",
        "when", "who", "which", "why", "can", "does", "do", "explain", "describe",
    }
)


class QAService:
    """Orchestrates codebase Q&A reasoning scoped strictly to an individual repository."""

    def _get_repository_graphs(
        self,
        repo_id: str,
    ) -> tuple[dict[str, Any], nx.DiGraph, dict[str, Any]]:
        """Load and cache (graph_data, nx_graph, analytics) for the target repository."""
        repo = get_repository(repo_id)
        if not repo:
            raise FileNotFoundError(f"Repository '{repo_id}' not found")

        if repo.status != "completed":
            raise ValueError(f"Repository indexing is in '{repo.status}' state; Q&A not ready")

        cached = repository_graph_cache.get(repo_id)
        if cached:
            graph_data, G = cached
        else:
            artifact_dir = settings.get_repo_artifact_dir(repo_id)
            code_graph_file = artifact_dir / "code_graph.json"
            if not code_graph_file.exists():
                raise FileNotFoundError(f"Code graph artifact not found for repository '{repo_id}'")

            with open(code_graph_file, "r", encoding="utf-8") as f:
                graph_data = json.load(f)

            G = build_networkx_graph(graph_data)
            repository_graph_cache.put(repo_id, graph_data, G)

        analytics = graph_analytics_service.get_repository_analytics(repo_id)
        return graph_data, G, analytics

    def _search_candidate_nodes(
        self,
        G: nx.DiGraph,
        analytics: dict[str, Any],
        question: str,
        limit: int = 6,
    ) -> list[dict[str, Any]]:
        """Search repository nodes using question tokens, weighted by centrality."""
        tokens = [
            t.lower()
            for t in re.findall(r"[a-zA-Z0-9_]{2,}", question)
            if t.lower() not in STOP_WORDS
        ]

        scored: list[tuple[float, str, dict[str, Any]]] = []
        node_metrics_map = {n["id"]: n for n in analytics.get("nodes", [])}

        for nid, data in G.nodes(data=True):
            score = 0.0
            label = str(data.get("label", nid)).lower()
            name = str(data.get("name", "")).lower()
            path = str(data.get("path", "")).lower()
            ntype = str(data.get("type", "")).lower()

            # Exact question match
            clean_q = question.strip().lower()
            if label == clean_q or label.rstrip("()") == clean_q:
                score += 50.0

            for tok in tokens:
                if tok == label or tok == label.rstrip("()"):
                    score += 35.0
                elif tok in label:
                    score += 20.0
                if tok == name:
                    score += 25.0
                elif tok in name:
                    score += 15.0
                if tok in path:
                    score += 10.0
                if tok == ntype:
                    score += 5.0

            if score > 0.0:
                n_analytics = node_metrics_map.get(nid, {})
                cent = n_analytics.get("metrics", {}).get("normalized_centrality", 0.0)
                score += cent * 15.0
                scored.append((score, nid, data))

        scored.sort(key=lambda item: item[0], reverse=True)

        candidates: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for _, nid, data in scored[:limit]:
            seen_ids.add(nid)
            candidates.append({"id": nid, **data})

        # Fallback if no direct keyword matches: pick top central entry points/nodes
        if not candidates and G.number_of_nodes() > 0:
            top_central = sorted(
                analytics.get("nodes", []),
                key=lambda item: item.get("metrics", {}).get("normalized_centrality", 0.0),
                reverse=True,
            )
            for n_entry in top_central[:limit]:
                nid = n_entry["id"]
                if G.has_node(nid):
                    candidates.append({"id": nid, **G.nodes[nid]})

        return candidates

    def _build_retrieval_context(
        self,
        repo_id: str,
        G: nx.DiGraph,
        analytics: dict[str, Any],
        candidates: list[dict[str, Any]],
    ) -> tuple[str, list[str], list[str]]:
        """Assemble structured topological context and safe source code snippets."""
        context_parts: list[str] = []
        relevant_files: list[str] = []
        relevant_symbols: list[str] = []
        node_metrics_map = {n["id"]: n for n in analytics.get("nodes", [])}
        source_dir = settings.get_repo_source_dir(repo_id)

        for c in candidates:
            nid = c["id"]
            label = c.get("label", nid)
            ntype = c.get("type", "unknown")
            path = c.get("path", "")
            if path and path not in relevant_files:
                relevant_files.append(path)
            if ntype in ("function", "method", "class", "async_function") and label not in relevant_symbols:
                relevant_symbols.append(label)

            n_analytics = node_metrics_map.get(nid, {})
            cent = n_analytics.get("metrics", {}).get("normalized_centrality", 0.0)
            cid = n_analytics.get("cluster_id", 0)

            node_header = [
                f"### Node: `{label}` (ID: `{nid}`)",
                f"- **Type**: {ntype}",
                f"- **Path**: `{path}`",
                f"- **Centrality Score**: {cent}",
                f"- **Cluster ID**: {cid}",
            ]

            # Inbound connections (who calls/imports this)
            inbound: list[str] = []
            for src, _, edata in G.in_edges(nid, data=True):
                src_label = G.nodes[src].get("label", src)
                rel = edata.get("type", "CALLS")
                inbound.append(f"`{src_label}` ({rel})")
            if inbound:
                node_header.append(f"- **Inbound (Called/Imported by)**: {', '.join(inbound[:5])}")

            # Outbound connections (what this calls/imports)
            outbound: list[str] = []
            for _, tgt, edata in G.out_edges(nid, data=True):
                tgt_label = G.nodes[tgt].get("label", tgt)
                rel = edata.get("type", "CALLS")
                outbound.append(f"`{tgt_label}` ({rel})")
            if outbound:
                node_header.append(f"- **Outbound (Calls/Imports)**: {', '.join(outbound[:5])}")

            # Safe Source Snippet Inspection (capped to 30 lines) with strict traversal protection
            if path:
                safe_rel = path.strip().replace("\\", "/").lstrip("/")
                if ".." not in Path(safe_rel).parts:
                    file_path = (source_dir.resolve() / safe_rel).resolve()
                    if (
                        file_path.is_relative_to(source_dir.resolve())
                        and file_path.is_file()
                        and not file_path.is_symlink()
                    ):
                        try:
                            with open(file_path, "r", encoding="utf-8", errors="replace") as sf:
                                lines = sf.readlines()
                            snippet = "".join(lines[:30]).strip()
                            if snippet:
                                node_header.append(f"```source\n{snippet}\n```")
                        except Exception:
                            pass

            context_parts.append("\n".join(node_header))

        full_context = "\n\n---\n\n".join(context_parts)
        return full_context, relevant_files, relevant_symbols

    async def answer_question(
        self,
        repo_id: str,
        question: str,
        history: Optional[list[dict[str, str]]] = None,
    ) -> QAResponse:
        """Process natural language question grounded in the repository's topology and source code."""
        start_time = time.perf_counter()

        graph_data, G, analytics = self._get_repository_graphs(repo_id)
        candidates = self._search_candidate_nodes(G, analytics, question)
        candidate_ids = [c["id"] for c in candidates]

        context, relevant_files, relevant_symbols = self._build_retrieval_context(
            repo_id, G, analytics, candidates
        )

        answer, highlighted_ids, used_model = await ai_client.generate_chat_answer(
            question=question,
            context=context,
            candidate_node_ids=candidate_ids,
            relevant_files=relevant_files,
            relevant_symbols=relevant_symbols,
        )

        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)

        return QAResponse(
            repository_id=repo_id,
            question=question,
            answer=answer,
            highlighted_node_ids=highlighted_ids,
            relevant_files=relevant_files,
            relevant_symbols=relevant_symbols,
            generation_duration_ms=elapsed_ms,
            model=used_model,
        )


# Global QA service singleton
qa_service = QAService()
