"""Graph query and traversal operations for Astral Cartographer's code graph."""

from __future__ import annotations

from collections import deque
from typing import Any, Optional


def find_node_by_id(
    graph: dict[str, Any],
    node_id: str,
) -> Optional[dict[str, Any]]:
    """Look up a node in the graph by its unique identifier.

    Args:
        graph: Serialized code graph dictionary.
        node_id: Target node ID.

    Returns:
        Matching node dictionary, or None if not found.
    """
    for node in graph.get("nodes", []):
        if node.get("id") == node_id:
            return node
    return None


def get_outgoing_neighbors(
    graph: dict[str, Any],
    node_id: str,
    edge_type: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Retrieve all nodes that are targets of outgoing edges from node_id.

    Args:
        graph: Serialized code graph dictionary.
        node_id: Source node ID.
        edge_type: Optional edge type to filter by (e.g. CALLS, IMPORTS).

    Returns:
        List of target node dictionaries.
    """
    node_map = {n["id"]: n for n in graph.get("nodes", [])}
    if node_id not in node_map:
        return []

    target_ids: list[str] = []
    for edge in graph.get("edges", []):
        if edge.get("source") == node_id:
            if edge_type is None or edge.get("type") == edge_type:
                target_id = edge.get("target")
                if target_id in node_map and target_id not in target_ids:
                    target_ids.append(target_id)

    return [node_map[tid] for tid in target_ids]


def get_incoming_neighbors(
    graph: dict[str, Any],
    node_id: str,
    edge_type: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Retrieve all nodes that point to node_id via incoming edges.

    Args:
        graph: Serialized code graph dictionary.
        node_id: Target node ID.
        edge_type: Optional edge type to filter by (e.g. CALLS, IMPORTS).

    Returns:
        List of source node dictionaries.
    """
    node_map = {n["id"]: n for n in graph.get("nodes", [])}
    if node_id not in node_map:
        return []

    source_ids: list[str] = []
    for edge in graph.get("edges", []):
        if edge.get("target") == node_id:
            if edge_type is None or edge.get("type") == edge_type:
                source_id = edge.get("source")
                if source_id in node_map and source_id not in source_ids:
                    source_ids.append(source_id)

    return [node_map[sid] for sid in source_ids]


def traverse_outgoing(
    graph: dict[str, Any],
    start_node_id: str,
    max_depth: int = 1,
    edge_types: Optional[list[str]] = None,
) -> list[dict[str, Any]]:
    """Traverse outgoing edges breadth-first up to a maximum depth.

    Args:
        graph: Serialized code graph dictionary.
        start_node_id: Root node ID to begin traversal.
        max_depth: Maximum edge distance (must be >= 0).
        edge_types: Optional list of edge types to follow.

    Returns:
        List of reached items with node dictionary, depth, and edge type.

    Raises:
        ValueError: If max_depth is negative.
    """
    if max_depth < 0:
        raise ValueError(f"max_depth must be non-negative, got {max_depth}")

    node_map = {n["id"]: n for n in graph.get("nodes", [])}
    if start_node_id not in node_map or max_depth == 0:
        return []

    allowed_types = set(edge_types) if edge_types else None

    # Adjacency list: source -> list of (target_id, edge_type)
    adj: dict[str, list[tuple[str, str]]] = {}
    for edge in graph.get("edges", []):
        etype = edge.get("type", "")
        if allowed_types is None or etype in allowed_types:
            adj.setdefault(edge.get("source", ""), []).append(
                (edge.get("target", ""), etype)
            )

    visited: set[str] = {start_node_id}
    queue: deque[tuple[str, int]] = deque([(start_node_id, 0)])
    results: list[dict[str, Any]] = []

    while queue:
        curr_id, curr_depth = queue.popleft()
        if curr_depth >= max_depth:
            continue

        for nxt_id, etype in adj.get(curr_id, []):
            if nxt_id not in visited and nxt_id in node_map:
                visited.add(nxt_id)
                next_depth = curr_depth + 1
                results.append(
                    {
                        "node": node_map[nxt_id],
                        "depth": next_depth,
                        "edge_type": etype,
                    }
                )
                queue.append((nxt_id, next_depth))

    return results


def find_path(
    graph: dict[str, Any],
    start_node_id: str,
    target_node_id: str,
    edge_types: Optional[list[str]] = None,
) -> Optional[list[str]]:
    """Find the shortest directed path between two nodes using Breadth-First Search.

    Args:
        graph: Serialized code graph dictionary.
        start_node_id: Starting node identifier.
        target_node_id: Destination node identifier.
        edge_types: Optional edge types to permit.

    Returns:
        List of node IDs forming the path, or None if unreachable.
    """
    node_map = {n["id"]: n for n in graph.get("nodes", [])}
    if start_node_id not in node_map or target_node_id not in node_map:
        return None

    if start_node_id == target_node_id:
        return [start_node_id]

    allowed_types = set(edge_types) if edge_types else None

    adj: dict[str, list[str]] = {}
    for edge in graph.get("edges", []):
        etype = edge.get("type", "")
        if allowed_types is None or etype in allowed_types:
            adj.setdefault(edge.get("source", ""), []).append(edge.get("target", ""))

    visited: set[str] = {start_node_id}
    queue: deque[list[str]] = deque([[start_node_id]])

    while queue:
        path = queue.popleft()
        last = path[-1]

        if last == target_node_id:
            return path

        for nxt in adj.get(last, []):
            if nxt not in visited and nxt in node_map:
                visited.add(nxt)
                queue.append(path + [nxt])

    return None


def impact_analysis(
    graph: dict[str, Any],
    target_node_id: str,
    max_depth: int = 5,
) -> dict[str, Any]:
    """Perform change impact analysis by traversing upstream dependencies.

    Determines all callers, importing files, and containing contexts that
    could be affected by a change to target_node_id.

    Args:
        graph: Serialized code graph dictionary.
        target_node_id: Node whose impact is being analyzed.
        max_depth: Maximum reverse traversal depth.

    Returns:
        Dictionary with target_node, impacted_nodes, impacted_edges, depth_reached.
    """
    if max_depth < 0:
        raise ValueError(f"max_depth must be non-negative, got {max_depth}")

    node_map = {n["id"]: n for n in graph.get("nodes", [])}
    target_node = node_map.get(target_node_id)
    if not target_node:
        return {
            "target_node": None,
            "impacted_nodes": [],
            "impacted_edges": [],
            "depth_reached": 0,
        }

    # Reverse adjacency list: target -> list of (source_id, edge)
    rev_adj: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for edge in graph.get("edges", []):
        rev_adj.setdefault(edge.get("target", ""), []).append(
            (edge.get("source", ""), edge)
        )

    visited_nodes: set[str] = {target_node_id}
    visited_edges: list[dict[str, Any]] = []
    seen_edge_ids: set[str] = set()

    queue: deque[tuple[str, int]] = deque([(target_node_id, 0)])
    max_depth_reached = 0

    while queue:
        curr_id, depth = queue.popleft()
        if depth >= max_depth:
            continue

        for src_id, edge in rev_adj.get(curr_id, []):
            edge_id = edge.get("id", f"{src_id}->{curr_id}")
            if edge_id not in seen_edge_ids:
                seen_edge_ids.add(edge_id)
                visited_edges.append(edge)

            if src_id not in visited_nodes and src_id in node_map:
                visited_nodes.add(src_id)
                new_depth = depth + 1
                if new_depth > max_depth_reached:
                    max_depth_reached = new_depth
                queue.append((src_id, new_depth))

    impacted_nodes = [
        node_map[nid] for nid in visited_nodes if nid != target_node_id
    ]

    # Check for unresolved references related to target or impacted nodes
    unresolved_refs = graph.get("unresolved_references", [])
    relevant_unresolved: list[dict[str, Any]] = []

    target_ids = {target_node_id} | {n["id"] for n in impacted_nodes}
    target_names: set[str] = set()
    if target_node:
        if target_node.get("name"):
            target_names.add(target_node["name"])
        qname = target_node.get("metadata", {}).get("qualified_name")
        if qname:
            target_names.add(qname)
    for n in impacted_nodes:
        if n.get("name"):
            target_names.add(n["name"])
        qname = n.get("metadata", {}).get("qualified_name")
        if qname:
            target_names.add(qname)

    for u in unresolved_refs:
        tname = u.get("target_name") or ""
        cands = u.get("candidates") or []
        expr = u.get("expression") or ""

        if any(c in target_ids for c in cands) or (tname and tname in target_names) or (expr in target_names):
            relevant_unresolved.append(u)

    is_complete = len(relevant_unresolved) == 0

    return {
        "target_node": target_node,
        "impacted_nodes": impacted_nodes,
        "impacted_edges": visited_edges,
        "depth_reached": max_depth_reached,
        "is_complete": is_complete,
        "has_unresolved_references": len(relevant_unresolved) > 0,
        "unresolved_references": relevant_unresolved,
    }
