"""Unified AI client adapter for Google Gemini with structured heuristic fallbacks.

Provides resilient, repository-grounded AI completions for Codebase Q&A,
Cluster Summaries, and Workflow Naming with context limits, timeouts, and
graceful offline degradation.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

GEMINI_API_URL: str = "https://generativelanguage.googleapis.com/v1beta/models"
REQUEST_TIMEOUT_SECONDS: float = 15.0


def has_gemini_key() -> bool:
    """Return True if a non-placeholder Gemini API key is configured."""
    key = (settings.gemini_api_key or "").strip()
    return bool(key and key != "your-gemini-api-key-here" and len(key) > 5)


class AIClient:
    """Resilient client adapter communicating with Gemini or using deterministic heuristics."""

    def __init__(self, timeout: float = REQUEST_TIMEOUT_SECONDS) -> None:
        self.timeout = timeout

    async def _call_gemini_rest(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.2,
        max_output_tokens: int = 1000,
    ) -> Optional[str]:
        """Make an asynchronous HTTP POST request to Google Gemini API."""
        if not has_gemini_key():
            return None

        model = settings.gemini_model or "gemini-3.1-flash-lite"
        url = f"{GEMINI_API_URL}/{model}:generateContent"
        headers = {
            "x-goog-api-key": settings.gemini_api_key.strip(),
            "Content-Type": "application/json",
        }

        contents: list[dict[str, Any]] = []
        if system_instruction:
            contents.append({"role": "user", "parts": [{"text": f"System Directive:\n{system_instruction}"}]})
            contents.append({"role": "model", "parts": [{"text": "Understood. I will strictly follow these directives."}]})

        contents.append({"role": "user", "parts": [{"text": prompt}]})

        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_output_tokens,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                res = await client.post(url, json=payload, headers=headers)
                if res.status_code == 200:
                    data = res.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts:
                            return parts[0].get("text", "").strip()
                else:
                    logger.warning(
                        "Gemini API returned status %d: %s",
                        res.status_code,
                        res.text[:200],
                    )
        except Exception as exc:
            logger.warning("Gemini API request failed (%s); falling back to heuristic", exc)

        return None

    async def generate_chat_answer(
        self,
        question: str,
        context: str,
        candidate_node_ids: list[str],
        relevant_files: list[str],
        relevant_symbols: list[str],
    ) -> tuple[str, list[str], str]:
        """Synthesize a structured Q&A response grounded in graph and source context."""
        system_prompt = (
            "You are Astrograph's Codebase Intelligence Agent. Explain architectural mechanisms, "
            "components, and execution flows within the codebase based solely on the provided topological "
            "graph context and code snippets.\n\n"
            "Format your answer in clear markdown.\n"
            "Return a JSON object at the very end enclosed in ```json and ``` with:\n"
            '{"highlighted_node_ids": ["<id1>", "<id2>"]}\n'
            "Only include node IDs that appear in the candidate list and are directly relevant."
        )

        user_prompt = (
            f"Question: {question}\n\n"
            f"Candidate Node IDs: {candidate_node_ids}\n\n"
            f"Topological Graph Context & Source Snippets:\n{context}"
        )

        try:
            raw_response = await self._call_gemini_rest(
                prompt=user_prompt,
                system_instruction=system_prompt,
                temperature=0.2,
                max_output_tokens=1500,
            )
        except Exception as exc:
            logger.warning("Gemini API call failed (%s); falling back to heuristic", exc)
            raw_response = None

        if raw_response:
            answer = raw_response
            highlighted: list[str] = []

            # Extract JSON block for highlighted node IDs if present
            json_match = re.search(r"```json\s*(\{.*?\})\s*```", raw_response, re.DOTALL)
            if json_match:
                try:
                    parsed = json.loads(json_match.group(1))
                    raw_ids = parsed.get("highlighted_node_ids", [])
                    highlighted = [nid for nid in raw_ids if nid in candidate_node_ids]
                    # Clean answer text from trailing JSON block
                    answer = raw_response[:json_match.start()].strip()
                except Exception:
                    pass

            if not highlighted:
                highlighted = candidate_node_ids[:4]

            active_model = settings.gemini_model or "gemini-3.1-flash-lite"
            return answer, highlighted, active_model

        # Deterministic Heuristic Fallback (offline or missing API credentials)
        ans, h_nodes = self._heuristic_chat_answer(
            question=question,
            candidate_node_ids=candidate_node_ids,
            relevant_files=relevant_files,
            relevant_symbols=relevant_symbols,
        )
        return ans, h_nodes, "static-heuristic-engine"

    def _heuristic_chat_answer(
        self,
        question: str,
        candidate_node_ids: list[str],
        relevant_files: list[str],
        relevant_symbols: list[str],
    ) -> tuple[str, list[str]]:
        """Generate high-precision architectural explanation without external model calls."""
        lines = [
            f"### Codebase Architectural Analysis for: *{question}*\n",
            "> [!NOTE]\n"
            "> *Statically Inferred Architecture (Offline Heuristic Mode — AI model response was unconfigured or unavailable)*\n",
            "Based on the static dependency topology, symbol indices, and graph structure:\n",
        ]

        if candidate_node_ids:
            lines.append(f"**Identified Key Components ({len(candidate_node_ids)} total):**")
            for nid in candidate_node_ids[:6]:
                lines.append(f"- Component node: `{nid}`")

        if relevant_files:
            lines.append("\n**Primary Source Locations:**")
            for fpath in relevant_files[:5]:
                lines.append(f"- `{fpath}`")

        if relevant_symbols:
            lines.append("\n**Key Resolved Symbols:**")
            for sym in relevant_symbols[:5]:
                lines.append(f"- `{sym}`")

        lines.append(
            "\n*The 3D visualization camera will highlight these architectural nodes and their connected call paths.*"
        )

        return "\n".join(lines), candidate_node_ids[:5]

    async def generate_cluster_summary(
        self,
        cluster_id: int,
        top_nodes: list[dict[str, Any]],
        languages: list[str],
        paths: list[str],
    ) -> str:
        """Synthesize a 1-sentence Galaxy summary describing a Louvain community cluster."""
        nodes_desc = "\n".join(
            f"- {n.get('label', n.get('id'))} ({n.get('type')} at `{n.get('path')}`, centrality: {n.get('centrality', 0.0)}): {n.get('name', '')}"
            for n in top_nodes[:5]
        )

        system_prompt = (
            "You are a software architect summarizing high-level module clusters in a 3D codebase visualizer.\n"
            "Provide a concise, 1-sentence Galaxy Summary (max 100 characters) describing "
            "the core domain/functional responsibility of this cluster. "
            "Example: 'Core routing, request logging, and authentication middleware.' "
            "Do NOT wrap in quotes."
        )

        user_prompt = (
            f"Cluster ID: {cluster_id}\n"
            f"Primary paths: {', '.join(paths) if paths else 'root'}\n"
            f"Languages: {', '.join(languages) if languages else 'Not specified'}\n"
            f"Top central nodes:\n{nodes_desc}\n\n"
            f"Galaxy Summary:"
        )

        try:
            raw_summary = await self._call_gemini_rest(
                prompt=user_prompt,
                system_instruction=system_prompt,
                temperature=0.2,
                max_output_tokens=150,
            )
        except Exception as exc:
            logger.warning("Gemini API call failed (%s); falling back to heuristic", exc)
            raw_summary = None

        if raw_summary:
            clean = raw_summary.strip().strip('"').strip("'").strip()
            if len(clean) > 130:
                clean = clean[:127] + "..."
            return clean

        return self._heuristic_cluster_summary(cluster_id, top_nodes, paths)

    def _heuristic_cluster_summary(
        self,
        cluster_id: int,
        top_nodes: list[dict[str, Any]],
        paths: list[str],
    ) -> str:
        """Deterministic heuristic cluster summary."""
        if not top_nodes:
            return f"Galaxy module {cluster_id} containing general application logic."

        primary_dir = paths[0] if paths else "core"
        labels = [n.get("label", n.get("id", "")).replace("()", "") for n in top_nodes[:3]]
        labels_str = ", ".join(labels) if labels else "components"

        return f"Galaxy module for '{primary_dir}' coordinating {labels_str}."

    async def generate_workflow_details(
        self,
        entry_label: str,
        entry_path: str,
        path_labels: list[str],
        node_count: int,
    ) -> tuple[str, str]:
        """Synthesize human-friendly workflow title and lifecycle summary."""
        chain = " -> ".join(path_labels[:6])

        system_prompt = (
            "You are describing a statically inferred execution workflow in a software codebase based on static call and import graphs.\n"
            "Provide two lines of output:\n"
            "NAME: [Short 3-5 word name, e.g. 'API Request & Handler Pipeline']\n"
            "DESC: [1 concise sentence describing what this statically inferred execution pathway accomplishes]"
        )

        user_prompt = (
            f"Entry point: {entry_label} at path '{entry_path}'\n"
            f"Execution sequence: {chain}\n"
            f"Total traversed components: {node_count}"
        )

        try:
            raw_text = await self._call_gemini_rest(
                prompt=user_prompt,
                system_instruction=system_prompt,
                temperature=0.2,
                max_output_tokens=200,
            )
        except Exception as exc:
            logger.warning("Gemini API call failed (%s); falling back to heuristic", exc)
            raw_text = None

        name = f"{entry_label} Execution Lifecycle"
        desc = f"Statically inferred execution pathway starting from {entry_label} traversing {node_count} components."

        if raw_text:
            for line in raw_text.splitlines():
                if line.startswith("NAME:"):
                    name = line.replace("NAME:", "").strip().strip('"')
                elif line.startswith("DESC:"):
                    desc = line.replace("DESC:", "").strip().strip('"')

        return name, desc


# Global AI client singleton
ai_client = AIClient()
