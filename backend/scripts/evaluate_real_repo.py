"""Evaluation script comparing baseline code graph with new code graph for real repository (Bottle).

Generates outputs in a separate evaluation directory without modifying baseline files.
"""

from __future__ import annotations

import json
from pathlib import Path
import time
from typing import Any

from app.graph.graph_builder import GraphBuilder, build_graph
from app.ingestion.scanner import scan_repository
from app.parsers.javascript_parser import parse_js_repository_inventory
from app.parsers.python_parser import parse_repository_inventory


def evaluate_bottle_repo() -> dict[str, Any]:
    repo_root = Path("data/repositories/repo_b7b0412d79ff/source").resolve()
    baseline_graph_path = Path("data/repositories/repo_b7b0412d79ff/artifacts/code_graph.json").resolve()
    eval_dir = Path("output/eval_bottle").resolve()
    eval_dir.mkdir(parents=True, exist_ok=True)

    print(f"Evaluating real repository at: {repo_root}")
    print(f"Baseline graph: {baseline_graph_path}")
    print(f"Evaluation directory: {eval_dir}")

    # 1. Load baseline graph
    with open(baseline_graph_path, "r", encoding="utf-8") as f:
        baseline_graph = json.load(f)

    # 2. Re-run analysis pipeline into eval_dir
    t0 = time.perf_counter()

    # Step A: Scan repository
    inv_data = scan_repository(repo_root, output_path=eval_dir / "repository_inventory.json")
    t_scan = time.perf_counter()

    # Step B: Parse Python AST
    py_analysis = parse_repository_inventory(
        inventory_path=eval_dir / "repository_inventory.json",
        repo_root=repo_root,
        output_path=eval_dir / "python_analysis.json",
    )
    t_py = time.perf_counter()

    # Step C: Parse JS/TS
    js_analysis = parse_js_repository_inventory(
        inventory_path=eval_dir / "repository_inventory.json",
        repo_root=repo_root,
        output_path=eval_dir / "javascript_analysis.json",
    )
    t_js = time.perf_counter()

    # Step D: Build graph
    new_graph = build_graph(
        repo_root=repo_root,
        inventory_path=eval_dir / "repository_inventory.json",
        analysis_path=[eval_dir / "python_analysis.json", eval_dir / "javascript_analysis.json"],
        output_path=eval_dir / "code_graph.json",
    )
    t_graph = time.perf_counter()

    total_time = t_graph - t0
    scan_time = t_scan - t0
    py_time = t_py - t_scan
    js_time = t_js - t_py
    graph_time = t_graph - t_js

    # 3. Calculate metrics for baseline vs new
    def get_stats(g: dict[str, Any]) -> dict[str, Any]:
        summary = g.get("summary", {})
        nodes = g.get("nodes", [])
        edges = g.get("edges", [])
        unresolved = g.get("unresolved_references", [])

        unres_by_status: dict[str, int] = {}
        for u in unresolved:
            st = u.get("status", "unresolved")
            unres_by_status[st] = unres_by_status.get(st, 0) + 1

        unres_by_kind: dict[str, int] = {}
        for u in unresolved:
            k = u.get("kind", "call")
            unres_by_kind[k] = unres_by_kind.get(k, 0) + 1

        unres_reasons: dict[str, int] = {}
        for u in unresolved:
            r = u.get("reason", "unknown")
            unres_reasons[r] = unres_reasons.get(r, 0) + 1

        top_reasons = sorted(unres_reasons.items(), key=lambda x: x[1], reverse=True)[:10]

        call_edges = [e for e in edges if e.get("type") == "CALLS"]
        strategies: dict[str, int] = {}
        for ce in call_edges:
            strat = ce.get("metadata", {}).get("strategy", "unknown")
            strategies[strat] = strategies.get(strat, 0) + 1

        return {
            "node_count": summary.get("node_count", len(nodes)),
            "edge_count": summary.get("edge_count", len(edges)),
            "nodes_by_type": summary.get("nodes_by_type", {}),
            "edges_by_type": summary.get("edges_by_type", {}),
            "resolved_calls": summary.get("resolved_calls", 0),
            "ambiguous_calls": summary.get("ambiguous_calls", 0),
            "unresolved_calls": summary.get("unresolved_calls", 0),
            "resolved_imports": summary.get("resolved_imports", 0),
            "unresolved_imports": summary.get("unresolved_imports", 0),
            "unresolved_total": len(unresolved),
            "unresolved_by_status": unres_by_status,
            "unresolved_by_kind": unres_by_kind,
            "strategies": strategies,
            "top_reasons": top_reasons,
        }

    base_stats = get_stats(baseline_graph)
    new_stats = get_stats(new_graph)

    # 4. Compare edges
    base_call_edges = {
        (e["source"], e["target"])
        for e in baseline_graph.get("edges", [])
        if e.get("type") == "CALLS"
    }
    new_call_edges = {
        (e["source"], e["target"])
        for e in new_graph.get("edges", [])
        if e.get("type") == "CALLS"
    }

    retained_calls = base_call_edges & new_call_edges
    removed_calls = base_call_edges - new_call_edges
    newly_added_calls = new_call_edges - base_call_edges

    # Edge endpoint integrity check on new graph
    node_ids = {n["id"] for n in new_graph.get("nodes", [])}
    broken_edges = [
        e for e in new_graph.get("edges", [])
        if e["source"] not in node_ids or e["target"] not in node_ids
    ]

    report = {
        "execution_time_seconds": {
            "total": round(total_time, 3),
            "scan": round(scan_time, 3),
            "python_parse": round(py_time, 3),
            "js_parse": round(js_time, 3),
            "graph_build": round(graph_time, 3),
        },
        "baseline": base_stats,
        "new": new_stats,
        "call_edges_comparison": {
            "retained_count": len(retained_calls),
            "removed_count": len(removed_calls),
            "newly_added_count": len(newly_added_calls),
            "sample_retained": [list(x) for x in list(retained_calls)[:5]],
            "sample_removed": [list(x) for x in list(removed_calls)[:5]],
            "sample_newly_added": [list(x) for x in list(newly_added_calls)[:5]],
        },
        "integrity": {
            "total_nodes": len(node_ids),
            "total_edges": len(new_graph.get("edges", [])),
            "broken_edges_count": len(broken_edges),
        },
    }

    # Save evaluation report
    report_path = eval_dir / "evaluation_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print("\n=== EVALUATION REPORT ===")
    print(f"Total time: {total_time:.2f}s (scan: {scan_time:.2f}s, py: {py_time:.2f}s, build: {graph_time:.2f}s)")
    print(f"Baseline Nodes: {base_stats['node_count']} -> New Nodes: {new_stats['node_count']}")
    print(f"Baseline Edges: {base_stats['edge_count']} -> New Edges: {new_stats['edge_count']}")
    print(f"Baseline CALLS: {base_stats['edges_by_type'].get('CALLS', 0)} -> New CALLS: {new_stats['edges_by_type'].get('CALLS', 0)}")
    print(f"Baseline IMPORTS: {base_stats['edges_by_type'].get('IMPORTS', 0)} -> New IMPORTS: {new_stats['edges_by_type'].get('IMPORTS', 0)}")
    print(f"Baseline Unresolved Refs: {base_stats['unresolved_total']} -> New Unresolved Refs: {new_stats['unresolved_total']}")
    print("Baseline status breakdown:", base_stats["unresolved_by_status"])
    print("New status breakdown:", new_stats["unresolved_by_status"])
    print("New resolution strategies:", new_stats["strategies"])
    print(f"Retained calls: {len(retained_calls)}, Removed calls: {len(removed_calls)}, Newly added calls: {len(newly_added_calls)}")
    print(f"Broken edge endpoints: {len(broken_edges)}")

    return report


if __name__ == "__main__":
    evaluate_bottle_repo()
