"""Tests validating code graph integrity, deterministic builds, and query correctness.

Phase 7 Requirements:
1. Every edge's source and target exist in the node set.
2. Every symbol ID identifies the intended symbol.
3. Identical function names in different scopes remain distinct.
4. Duplicate edges are handled consistently.
5. Source locations remain accurate.
6. Repeated builds from unchanged inputs are deterministic.
7. Incoming and outgoing graph queries produce expected results.
8. Path finding follows actual supported edges.
9. Impact analysis does not silently claim completeness when references remain unresolved.
10. Missing or malformed analysis records are handled safely.
"""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from app.graph.graph_builder import GraphBuilder, build_graph
from app.graph.graph_queries import (
    find_node_by_id,
    find_path,
    get_incoming_neighbors,
    get_outgoing_neighbors,
    impact_analysis,
    traverse_outgoing,
)
from app.graph.models import (
    EDGE_TYPE_CALLS,
    EDGE_TYPE_CONTAINS,
    EDGE_TYPE_DEFINES,
    EDGE_TYPE_IMPORTS,
    STATUS_UNRESOLVED,
    UnresolvedReference,
)
from app.ingestion.scanner import scan_repository
from app.parsers.python_parser import parse_repository_inventory


class TestGraphIntegrityAndQueries(unittest.TestCase):
    """Test suite for Phase 7 graph integrity and queries."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo_dir = Path(self.temp_dir.name)

        # Create a small multi-module repository
        (self.repo_dir / "pkg").mkdir()
        (self.repo_dir / "pkg" / "__init__.py").write_text("", encoding="utf-8")
        (self.repo_dir / "pkg" / "utils.py").write_text(
            "def helper():\n"
            "    return 'help'\n"
            "\n"
            "class Tool:\n"
            "    def run(self):\n"
            "        return helper()\n",
            encoding="utf-8",
        )
        (self.repo_dir / "main.py").write_text(
            "from pkg.utils import helper, Tool\n"
            "\n"
            "def execute():\n"
            "    t = Tool()\n"
            "    return helper()\n"
            "\n"
            "def helper():\n"
            "    # Same name as pkg.utils.helper, but local scope\n"
            "    return 'local'\n",
            encoding="utf-8",
        )

        # Run scan and parse
        self.inv = scan_repository(self.repo_dir)
        inv_file = self.repo_dir / "inventory.json"
        with open(inv_file, "w", encoding="utf-8") as f:
            json.dump(self.inv, f)
        self.analysis = parse_repository_inventory(inv_file, self.repo_dir)
        builder = GraphBuilder(self.repo_dir, self.inv, self.analysis)
        self.graph = builder.build().to_dict()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_01_endpoints_exist_in_node_set(self) -> None:
        """Requirement 1: Every edge's source and target exist in the node set."""
        node_ids = {n["id"] for n in self.graph["nodes"]}
        for edge in self.graph["edges"]:
            self.assertIn(
                edge["source"],
                node_ids,
                f"Edge source {edge['source']} missing from nodes",
            )
            self.assertIn(
                edge["target"],
                node_ids,
                f"Edge target {edge['target']} missing from nodes",
            )

    def test_02_symbol_ids_identify_intended_symbols(self) -> None:
        """Requirement 2: Every symbol ID uniquely identifies the intended symbol."""
        symbols = [n for n in self.graph["nodes"] if n["id"].startswith("symbol:")]
        self.assertGreater(len(symbols), 0)
        seen_ids = set()
        for sym in symbols:
            self.assertNotIn(sym["id"], seen_ids)
            seen_ids.add(sym["id"])
            meta = sym.get("metadata", {})
            self.assertIn("file_path", meta)
            self.assertIn("qualified_name", meta)
            self.assertIn("kind", meta)

    def test_03_identical_function_names_in_different_scopes_distinct(self) -> None:
        """Requirement 3: Identical function names in different scopes remain distinct."""
        helper_nodes = [
            n for n in self.graph["nodes"]
            if n.get("name") == "helper" and n.get("type") == "function"
        ]
        self.assertEqual(len(helper_nodes), 2)
        node_ids = {n["id"] for n in helper_nodes}
        self.assertEqual(len(node_ids), 2)
        files = {n["metadata"]["file_path"] for n in helper_nodes}
        self.assertEqual(files, {"main.py", "pkg/utils.py"})

    def test_04_duplicate_edges_handled_consistently(self) -> None:
        """Requirement 4: Duplicate edges are handled consistently with line preservation."""
        builder = GraphBuilder(self.repo_dir, self.inv, self.analysis)
        # Add test nodes
        builder.nodes["file:a.py"] = builder.nodes.get("file:main.py")
        builder.nodes["file:b.py"] = builder.nodes.get("file:pkg/utils.py")

        added1 = builder._add_edge(
            "file:a.py", "file:b.py", EDGE_TYPE_IMPORTS, {"line": 10}
        )
        self.assertTrue(added1)

        # Duplicate edge with a different line number
        added2 = builder._add_edge(
            "file:a.py", "file:b.py", EDGE_TYPE_IMPORTS, {"line": 20}
        )
        self.assertFalse(added2)

        edge = builder.edges[("file:a.py", "file:b.py", EDGE_TYPE_IMPORTS)]
        self.assertEqual(edge.metadata.get("lines"), [10, 20])

    def test_05_source_locations_accurate(self) -> None:
        """Requirement 5: Source locations remain accurate."""
        for sym in self.graph["nodes"]:
            if sym["type"] in ("function", "method", "class"):
                meta = sym["metadata"]
                self.assertIsNotNone(meta.get("lineno"))
                self.assertGreater(meta["lineno"], 0)

    def test_06_deterministic_repeated_builds(self) -> None:
        """Requirement 6: Repeated builds from unchanged inputs are deterministic."""
        builder1 = GraphBuilder(self.repo_dir, self.inv, self.analysis)
        g1 = builder1.build().to_dict()

        builder2 = GraphBuilder(self.repo_dir, self.inv, self.analysis)
        g2 = builder2.build().to_dict()

        self.assertEqual(
            json.dumps(g1, sort_keys=True),
            json.dumps(g2, sort_keys=True),
        )

    def test_07_incoming_and_outgoing_queries(self) -> None:
        """Requirement 7: Incoming and outgoing graph queries produce expected results."""
        main_file = "file:main.py"
        out_neighbors = get_outgoing_neighbors(self.graph, main_file)
        self.assertGreater(len(out_neighbors), 0)

        # Incoming neighbors for pkg/utils.py should include main.py via IMPORTS
        utils_file = "file:pkg/utils.py"
        in_neighbors = get_incoming_neighbors(self.graph, utils_file, edge_type=EDGE_TYPE_IMPORTS)
        in_ids = [n["id"] for n in in_neighbors]
        self.assertIn("file:main.py", in_ids)

        # BFS traversal
        traversed = traverse_outgoing(self.graph, main_file, max_depth=2)
        self.assertGreater(len(traversed), 0)

    def test_08_path_finding_follows_actual_edges(self) -> None:
        """Requirement 8: Path finding follows actual supported edges."""
        path = find_path(self.graph, "file:main.py", "file:pkg/utils.py")
        self.assertIsNotNone(path)
        self.assertEqual(path[0], "file:main.py")
        self.assertEqual(path[-1], "file:pkg/utils.py")

        # Unreachable target returns None
        repo_node_id = f"repository:{self.repo_dir.name}"
        reverse_path = find_path(
            self.graph, "file:pkg/utils.py", repo_node_id, edge_types=[EDGE_TYPE_CALLS]
        )
        self.assertIsNone(reverse_path)

    def test_09_impact_analysis_reports_completeness(self) -> None:
        """Requirement 9: Impact analysis does not silently claim completeness when references remain unresolved."""
        # 1. Target with no unresolved references -> is_complete = True
        impact_clean = impact_analysis(self.graph, "file:pkg/utils.py")
        self.assertTrue(impact_clean["is_complete"])
        self.assertFalse(impact_clean["has_unresolved_references"])

        # 2. Simulate unresolved reference targeting a symbol
        graph_with_unresolved = dict(self.graph)
        graph_with_unresolved["unresolved_references"] = [
            {
                "kind": "call",
                "source_file": "client.py",
                "caller_id": None,
                "expression": "helper()",
                "target_name": "helper",
                "lineno": 15,
                "status": STATUS_UNRESOLVED,
                "candidates": ["symbol:pkg/utils.py::helper:function:1"],
                "reason": "Ambiguous callee",
            }
        ]

        target_sym_id = "symbol:pkg/utils.py::helper:function:1"
        impact_flagged = impact_analysis(graph_with_unresolved, target_sym_id)
        self.assertFalse(impact_flagged["is_complete"])
        self.assertTrue(impact_flagged["has_unresolved_references"])
        self.assertEqual(len(impact_flagged["unresolved_references"]), 1)

    def test_10_missing_or_malformed_analysis_records_handled_safely(self) -> None:
        """Requirement 10: Missing or malformed analysis records are handled safely."""
        empty_inv = {"repository_name": "empty_repo", "files": []}
        malformed_analysis = {
            "summary": {},
            "symbols": [{"id": "bad_sym", "name": "bad", "kind": "unknown_kind", "file_path": "missing.py"}],
            "imports": [{"file_path": "missing.py", "module": None}],
            "calls": [{"file_path": "missing.py", "callee": None}],
        }
        builder = GraphBuilder(self.repo_dir, empty_inv, malformed_analysis)
        # Should not raise exception
        graph = builder.build()
        self.assertIsNotNone(graph)
        self.assertIn("repository:empty_repo", [n.id for n in graph.nodes])


if __name__ == "__main__":
    unittest.main()
