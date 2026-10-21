"""Automated unit and integration tests for Astral Cartographer's Code Graph Builder and Symbol Resolver."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest

from app.graph.graph_builder import (
    GRAPH_SCHEMA_VERSION,
    GraphBuilder,
    build_graph,
    main,
)
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
    NODE_TYPE_CLASS,
    NODE_TYPE_DIRECTORY,
    NODE_TYPE_FILE,
    NODE_TYPE_FUNCTION,
    NODE_TYPE_METHOD,
    NODE_TYPE_REPOSITORY,
    STATUS_AMBIGUOUS,
    STATUS_EXTERNAL,
    STATUS_RESOLVED,
    STATUS_UNRESOLVED,
)
from app.ingestion.scanner import scan_repository
from app.parsers.python_parser import parse_repository_inventory


class TestGraphBuilder(unittest.TestCase):
    """Test suite covering all requirements and scenarios for Step 3 Code Graph Builder."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo_path = Path(self.temp_dir.name).resolve()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _create_sample_graph(self) -> dict:
        """Helper to create a multi-module sample project with inventory and analysis."""
        # 1. Module A: payments.py
        payments_code = (
            "def validate_payment(amount: float) -> bool:\n"
            "    return amount > 0\n"
            "\n"
            "class PaymentProcessor:\n"
            "    def process(self, amount: float):\n"
            "        return self.validate_internal(amount)\n"
            "    def validate_internal(self, amount: float):\n"
            "        return validate_payment(amount)\n"
        )
        (self.repo_path / "payments.py").write_text(payments_code, encoding="utf-8")

        # 2. Module B: checkout.py
        checkout_code = (
            "from payments import validate_payment as val, PaymentProcessor\n"
            "\n"
            "def do_checkout(total: float):\n"
            "    val(total)\n"
            "    proc = PaymentProcessor()\n"
            "\n"
            "do_checkout(100.0)\n"
        )
        (self.repo_path / "checkout.py").write_text(checkout_code, encoding="utf-8")

        # 3. Non-code file: README.md
        (self.repo_path / "README.md").write_text("# Shop", encoding="utf-8")

        # Scan and parse
        inv_file = self.repo_path / "output" / "repository_inventory.json"
        scan_repository(self.repo_path, output_path=inv_file)

        ana_file = self.repo_path / "output" / "python_analysis.json"
        parse_repository_inventory(inv_file, self.repo_path, output_path=ana_file)

        graph_file = self.repo_path / "output" / "code_graph.json"
        return build_graph(self.repo_path, inv_file, ana_file, output_path=graph_file)

    # 1. Repository, directory, and file nodes
    def test_01_repo_dir_and_file_nodes(self) -> None:
        sub_dir = self.repo_path / "src" / "pkg"
        sub_dir.mkdir(parents=True)
        (sub_dir / "mod.py").write_text("x = 1\n", encoding="utf-8")

        inv_file = self.repo_path / "inv.json"
        scan_repository(self.repo_path, output_path=inv_file)
        ana_file = self.repo_path / "ana.json"
        parse_repository_inventory(inv_file, self.repo_path, output_path=ana_file)

        graph = build_graph(self.repo_path, inv_file, ana_file)
        nodes_by_id = {n["id"]: n for n in graph["nodes"]}

        # Check repository node
        repo_id = f"repository:{self.repo_path.name}"
        self.assertIn(repo_id, nodes_by_id)
        self.assertEqual(nodes_by_id[repo_id]["type"], NODE_TYPE_REPOSITORY)

        # Check directory nodes
        self.assertIn("directory:src", nodes_by_id)
        self.assertIn("directory:src/pkg", nodes_by_id)
        self.assertEqual(nodes_by_id["directory:src"]["type"], NODE_TYPE_DIRECTORY)

        # Check file node
        self.assertIn("file:src/pkg/mod.py", nodes_by_id)
        self.assertEqual(nodes_by_id["file:src/pkg/mod.py"]["type"], NODE_TYPE_FILE)
        self.assertEqual(nodes_by_id["file:src/pkg/mod.py"]["metadata"]["language"], "Python")

    # 2. Function, method, and class nodes
    def test_02_function_method_and_class_nodes(self) -> None:
        graph = self._create_sample_graph()
        nodes_by_type: dict[str, list[dict]] = {}
        for n in graph["nodes"]:
            nodes_by_type.setdefault(n["type"], []).append(n)

        self.assertIn(NODE_TYPE_CLASS, nodes_by_type)
        self.assertIn(NODE_TYPE_FUNCTION, nodes_by_type)
        self.assertIn(NODE_TYPE_METHOD, nodes_by_type)

        cls_nodes = [n for n in nodes_by_type[NODE_TYPE_CLASS] if n["name"] == "PaymentProcessor"]
        self.assertEqual(len(cls_nodes), 1)

        meth_names = {n["name"] for n in nodes_by_type[NODE_TYPE_METHOD]}
        self.assertIn("process", meth_names)
        self.assertIn("validate_internal", meth_names)

        func_names = {n["name"] for n in nodes_by_type[NODE_TYPE_FUNCTION]}
        self.assertIn("validate_payment", func_names)
        self.assertIn("do_checkout", func_names)

    # 3. File-to-symbol DEFINES edges
    def test_03_file_to_symbol_defines_edges(self) -> None:
        graph = self._create_sample_graph()
        defines_edges = [e for e in graph["edges"] if e["type"] == EDGE_TYPE_DEFINES]

        sources = {e["source"] for e in defines_edges}
        self.assertIn("file:payments.py", sources)
        self.assertIn("file:checkout.py", sources)

        # Top level function defined by payments.py
        targets_from_payments = [e["target"] for e in defines_edges if e["source"] == "file:payments.py"]
        self.assertTrue(any("validate_payment:function" in t for t in targets_from_payments))
        self.assertTrue(any("PaymentProcessor:class" in t for t in targets_from_payments))

    # 4. Directory and class containment
    def test_04_directory_and_class_containment(self) -> None:
        graph = self._create_sample_graph()
        contains_edges = [e for e in graph["edges"] if e["type"] == EDGE_TYPE_CONTAINS]

        # Class containment: PaymentProcessor -> process & validate_internal
        class_contains = [
            e for e in contains_edges if "PaymentProcessor:class" in e["source"]
        ]
        self.assertEqual(len(class_contains), 2)
        targets = [e["target"] for e in class_contains]
        self.assertTrue(any("process:method" in t for t in targets))
        self.assertTrue(any("validate_internal:method" in t for t in targets))

    # 5. A direct call resolving to a unique target
    def test_05_direct_call_unique_target(self) -> None:
        code = (
            "def target_func():\n"
            "    return 42\n"
            "\n"
            "def caller_func():\n"
            "    return target_func()\n"
        )
        (self.repo_path / "direct.py").write_text(code, encoding="utf-8")

        inv_file = self.repo_path / "inv.json"
        scan_repository(self.repo_path, output_path=inv_file)
        ana_file = self.repo_path / "ana.json"
        parse_repository_inventory(inv_file, self.repo_path, output_path=ana_file)

        graph = build_graph(self.repo_path, inv_file, ana_file)
        calls_edges = [e for e in graph["edges"] if e["type"] == EDGE_TYPE_CALLS]

        self.assertEqual(len(calls_edges), 1)
        call_edge = calls_edges[0]
        self.assertTrue("caller_func:function" in call_edge["source"])
        self.assertTrue("target_func:function" in call_edge["target"])
        self.assertEqual(call_edge["metadata"]["strategy"], "same_module")

    # 6. A call resolved using an imported alias
    def test_06_call_resolved_using_imported_alias(self) -> None:
        graph = self._create_sample_graph()
        calls_edges = [e for e in graph["edges"] if e["type"] == EDGE_TYPE_CALLS]

        # In checkout.py: do_checkout calls val(total) which is alias of validate_payment
        alias_calls = [
            e for e in calls_edges
            if "do_checkout" in e["source"] and "validate_payment" in e["target"]
        ]
        self.assertEqual(len(alias_calls), 1)
        self.assertEqual(alias_calls[0]["metadata"]["strategy"], "imported_alias")

    # 7. Local IMPORTS edges
    def test_07_local_imports_edges(self) -> None:
        graph = self._create_sample_graph()
        import_edges = [e for e in graph["edges"] if e["type"] == EDGE_TYPE_IMPORTS]

        # checkout.py -> payments.py
        self.assertEqual(len(import_edges), 1)
        edge = import_edges[0]
        self.assertEqual(edge["source"], "file:checkout.py")
        self.assertEqual(edge["target"], "file:payments.py")

    # 8. Relative import resolution in a basic package
    def test_08_relative_import_resolution_in_package(self) -> None:
        pkg = self.repo_path / "pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("", encoding="utf-8")
        (pkg / "service.py").write_text("def run(): pass\n", encoding="utf-8")
        (pkg / "controller.py").write_text(
            "from .service import run\ndef handle(): run()\n", encoding="utf-8"
        )

        inv_file = self.repo_path / "inv.json"
        scan_repository(self.repo_path, output_path=inv_file)
        ana_file = self.repo_path / "ana.json"
        parse_repository_inventory(inv_file, self.repo_path, output_path=ana_file)

        graph = build_graph(self.repo_path, inv_file, ana_file)
        import_edges = [e for e in graph["edges"] if e["type"] == EDGE_TYPE_IMPORTS]

        self.assertEqual(len(import_edges), 1)
        edge = import_edges[0]
        self.assertEqual(edge["source"], "file:pkg/controller.py")
        self.assertEqual(edge["target"], "file:pkg/service.py")

        calls_edges = [e for e in graph["edges"] if e["type"] == EDGE_TYPE_CALLS]
        self.assertEqual(len(calls_edges), 1)
        self.assertTrue("service.py::run:function" in calls_edges[0]["target"])

    # 9. Duplicate function names across modules
    def test_09_duplicate_function_names_across_modules(self) -> None:
        # mod_a.py defines compute()
        (self.repo_path / "mod_a.py").write_text(
            "def compute(): return 1\ndef run(): compute()\n", encoding="utf-8"
        )
        # mod_b.py defines compute()
        (self.repo_path / "mod_b.py").write_text(
            "def compute(): return 2\ndef execute(): compute()\n", encoding="utf-8"
        )

        inv_file = self.repo_path / "inv.json"
        scan_repository(self.repo_path, output_path=inv_file)
        ana_file = self.repo_path / "ana.json"
        parse_repository_inventory(inv_file, self.repo_path, output_path=ana_file)

        graph = build_graph(self.repo_path, inv_file, ana_file)
        calls_edges = [e for e in graph["edges"] if e["type"] == EDGE_TYPE_CALLS]

        # Each run() and execute() must resolve to its OWN module's compute()
        for edge in calls_edges:
            if "mod_a.py::run" in edge["source"]:
                self.assertTrue("mod_a.py::compute" in edge["target"])
            elif "mod_b.py::execute" in edge["source"]:
                self.assertTrue("mod_b.py::compute" in edge["target"])

    # 10. Ambiguous call references remaining unresolved or marked ambiguous
    def test_10_ambiguous_calls_marked_ambiguous(self) -> None:
        # file1 has process()
        (self.repo_path / "file1.py").write_text("def process(): pass\n", encoding="utf-8")
        # file2 has process()
        (self.repo_path / "file2.py").write_text("def process(): pass\n", encoding="utf-8")
        # caller.py calls process() without importing either
        (self.repo_path / "caller.py").write_text(
            "def invoke(): process()\n", encoding="utf-8"
        )

        inv_file = self.repo_path / "inv.json"
        scan_repository(self.repo_path, output_path=inv_file)
        ana_file = self.repo_path / "ana.json"
        parse_repository_inventory(inv_file, self.repo_path, output_path=ana_file)

        graph = build_graph(self.repo_path, inv_file, ana_file)
        calls_edges = [e for e in graph["edges"] if e["type"] == EDGE_TYPE_CALLS]

        # No call edge should be created for the ambiguous call
        self.assertEqual(len(calls_edges), 0)

        # Must appear in unresolved_references as ambiguous with candidate IDs
        ambiguous_refs = [
            r for r in graph["unresolved_references"]
            if r["kind"] == "call" and r["status"] == STATUS_AMBIGUOUS
        ]
        self.assertEqual(len(ambiguous_refs), 1)
        ref = ambiguous_refs[0]
        self.assertEqual(len(ref["candidates"]), 2)
        self.assertTrue(any("file1.py" in c for c in ref["candidates"]))
        self.assertTrue(any("file2.py" in c for c in ref["candidates"]))

    # 11. Unresolved and external imports
    def test_11_unresolved_and_external_imports(self) -> None:
        code = (
            "import os\n"
            "import sys\n"
            "import non_existent_pkg\n"
        )
        (self.repo_path / "imports_test.py").write_text(code, encoding="utf-8")

        inv_file = self.repo_path / "inv.json"
        scan_repository(self.repo_path, output_path=inv_file)
        ana_file = self.repo_path / "ana.json"
        parse_repository_inventory(inv_file, self.repo_path, output_path=ana_file)

        graph = build_graph(self.repo_path, inv_file, ana_file)
        self.assertEqual(len([e for e in graph["edges"] if e["type"] == EDGE_TYPE_IMPORTS]), 0)

        unresolved_imps = [r for r in graph["unresolved_references"] if r["kind"] == "import"]
        self.assertEqual(len(unresolved_imps), 3)

        statuses = {r["status"] for r in unresolved_imps}
        self.assertIn(STATUS_EXTERNAL, statuses)

    # 12. Module-level call expressions
    def test_12_module_level_call_expressions(self) -> None:
        code = (
            "def initialize(): pass\n"
            "initialize()\n"
        )
        (self.repo_path / "startup.py").write_text(code, encoding="utf-8")

        inv_file = self.repo_path / "inv.json"
        scan_repository(self.repo_path, output_path=inv_file)
        ana_file = self.repo_path / "ana.json"
        parse_repository_inventory(inv_file, self.repo_path, output_path=ana_file)

        graph = build_graph(self.repo_path, inv_file, ana_file)
        call_edges = [e for e in graph["edges"] if e["type"] == EDGE_TYPE_CALLS]

        self.assertEqual(len(call_edges), 1)
        edge = call_edges[0]
        self.assertEqual(edge["source"], "file:startup.py")
        self.assertTrue("initialize:function" in edge["target"])
        self.assertTrue(edge["metadata"]["is_module_level"])

    # 13. Unknown caller or target symbol IDs (no broken edges)
    def test_13_unknown_caller_or_target_never_creates_broken_edge(self) -> None:
        inv_data = {
            "schema_version": 1,
            "repository_name": "GhostRepo",
            "files": [{"path": "ghost.py", "language": "Python"}],
        }
        # Analysis with a call referencing a non-existent caller and non-existent target
        ana_data = {
            "schema_version": 1,
            "repository_name": "GhostRepo",
            "symbols": [],
            "imports": [],
            "calls": [
                {
                    "callee": "phantom_func",
                    "callee_name": "phantom_func",
                    "file_path": "ghost.py",
                    "lineno": 1,
                    "caller": "phantom_caller",
                    "caller_symbol_id": "ghost.py::phantom_caller:function:999",
                    "is_module_level": False,
                }
            ],
            "parse_errors": [],
        }

        builder = GraphBuilder(self.repo_path, inv_data, ana_data)
        graph = builder.build().to_dict()

        # No CALLS edge should be created
        self.assertEqual(len(graph["edges"]), 1)  # Only repository -> file contains
        self.assertEqual(graph["summary"]["resolved_calls"], 0)
        self.assertEqual(graph["summary"]["unresolved_calls"], 1)

    # 14. Duplicate-edge prevention
    def test_14_duplicate_edge_prevention(self) -> None:
        code = (
            "def worker(): pass\n"
            "def run():\n"
            "    worker()\n"
            "    worker()\n"  # Second call to same target in same function
        )
        (self.repo_path / "dup.py").write_text(code, encoding="utf-8")

        inv_file = self.repo_path / "inv.json"
        scan_repository(self.repo_path, output_path=inv_file)
        ana_file = self.repo_path / "ana.json"
        parse_repository_inventory(inv_file, self.repo_path, output_path=ana_file)

        graph = build_graph(self.repo_path, inv_file, ana_file)
        call_edges = [e for e in graph["edges"] if e["type"] == EDGE_TYPE_CALLS]

        # Exactly 1 CALLS edge should exist between run and worker
        self.assertEqual(len(call_edges), 1)
        # Metadata should record both line numbers
        self.assertEqual(len(call_edges[0]["metadata"]["lines"]), 2)

    # 15. Missing files and malformed analysis JSON
    def test_15_missing_files_and_malformed_json_handling(self) -> None:
        non_existent = self.repo_path / "non_existent.json"
        with self.assertRaises(FileNotFoundError):
            build_graph(self.repo_path, non_existent, non_existent)

        malformed = self.repo_path / "bad.json"
        malformed.write_text("NOT A JSON {{{", encoding="utf-8")
        with self.assertRaises(json.JSONDecodeError):
            build_graph(self.repo_path, malformed, malformed)

    # 16. Unsafe or out-of-root paths
    def test_16_out_of_root_repo_validation(self) -> None:
        with self.assertRaises(FileNotFoundError):
            build_graph(self.repo_path / "not_there", "inv.json", "ana.json")

        file_as_root = self.repo_path / "file.txt"
        file_as_root.write_text("not a dir", encoding="utf-8")
        with self.assertRaises(NotADirectoryError):
            build_graph(file_as_root, "inv.json", "ana.json")

    # 17. Empty repositories and empty analysis results
    def test_17_empty_repositories(self) -> None:
        inv_file = self.repo_path / "empty_inv.json"
        with open(inv_file, "w", encoding="utf-8") as f:
            json.dump({"schema_version": 1, "repository_name": "Empty", "files": []}, f)

        ana_file = self.repo_path / "empty_ana.json"
        with open(ana_file, "w", encoding="utf-8") as f:
            json.dump({"schema_version": 1, "repository_name": "Empty", "symbols": [], "imports": [], "calls": []}, f)

        graph = build_graph(self.repo_path, inv_file, ana_file)
        self.assertEqual(graph["summary"]["node_count"], 1)  # Repository node
        self.assertEqual(graph["summary"]["edge_count"], 0)
        self.assertEqual(len(graph["nodes"]), 1)
        self.assertEqual(graph["edges"], [])

    # 18. Files without parsed symbols (annotated analysis status)
    def test_18_files_without_parsed_symbols(self) -> None:
        (self.repo_path / "notes.txt").write_text("Just notes", encoding="utf-8")
        inv_file = self.repo_path / "inv.json"
        scan_repository(self.repo_path, output_path=inv_file)

        ana_file = self.repo_path / "ana.json"
        parse_repository_inventory(inv_file, self.repo_path, output_path=ana_file)

        graph = build_graph(self.repo_path, inv_file, ana_file)
        file_node = find_node_by_id(graph, "file:notes.txt")

        self.assertIsNotNone(file_node)
        self.assertEqual(file_node["metadata"]["language"], "Unknown")
        self.assertFalse(file_node["metadata"]["analyzed"])

    # 19. Stable node IDs, edge IDs, ordering, and output across repeated runs
    def test_19_stable_output_across_repeated_runs(self) -> None:
        self._create_sample_graph()
        inv_file = self.repo_path / "output" / "repository_inventory.json"
        ana_file = self.repo_path / "output" / "python_analysis.json"

        graph1 = build_graph(self.repo_path, inv_file, ana_file)
        graph2 = build_graph(self.repo_path, inv_file, ana_file)

        json1 = json.dumps(graph1, sort_keys=True)
        json2 = json.dumps(graph2, sort_keys=True)
        self.assertEqual(json1, json2)

    # 20. Correct graph summary counts
    def test_20_graph_summary_counts(self) -> None:
        graph = self._create_sample_graph()
        summary = graph["summary"]

        self.assertEqual(summary["node_count"], len(graph["nodes"]))
        self.assertEqual(summary["edge_count"], len(graph["edges"]))
        self.assertEqual(sum(summary["nodes_by_type"].values()), len(graph["nodes"]))
        self.assertEqual(sum(summary["edges_by_type"].values()), len(graph["edges"]))

    # 21. Basic queries: incoming, outgoing, depth-limited, path
    def test_21_graph_queries(self) -> None:
        graph = self._create_sample_graph()

        # 1. find_node_by_id
        repo_id = f"repository:{self.repo_path.name}"
        repo_node = find_node_by_id(graph, repo_id)
        self.assertIsNotNone(repo_node)
        self.assertIsNone(find_node_by_id(graph, "non_existent"))

        # 2. get_outgoing_neighbors
        outgoing_repo = get_outgoing_neighbors(graph, repo_id)
        self.assertGreater(len(outgoing_repo), 0)

        # 3. get_incoming_neighbors
        pmt_file_id = "file:payments.py"
        incoming_pmt = get_incoming_neighbors(graph, pmt_file_id, edge_type=EDGE_TYPE_IMPORTS)
        self.assertEqual(len(incoming_pmt), 1)
        self.assertEqual(incoming_pmt[0]["id"], "file:checkout.py")

        # 4. traverse_outgoing
        reached = traverse_outgoing(graph, repo_id, max_depth=2)
        self.assertGreater(len(reached), 0)
        self.assertTrue(all(r["depth"] in (1, 2) for r in reached))

        # 5. find_path
        chk_file_id = "file:checkout.py"
        path = find_path(graph, chk_file_id, pmt_file_id)
        self.assertEqual(path, [chk_file_id, pmt_file_id])

        # 6. impact_analysis
        impact = impact_analysis(graph, pmt_file_id)
        impacted_ids = [n["id"] for n in impact["impacted_nodes"]]
        self.assertIn("file:checkout.py", impacted_ids)

    # 22. Invalid query inputs and unknown node IDs
    def test_22_invalid_query_inputs(self) -> None:
        graph = self._create_sample_graph()

        with self.assertRaises(ValueError):
            traverse_outgoing(graph, "file:payments.py", max_depth=-1)

        with self.assertRaises(ValueError):
            impact_analysis(graph, "file:payments.py", max_depth=-5)

        self.assertEqual(get_outgoing_neighbors(graph, "ghost_id"), [])
        self.assertEqual(get_incoming_neighbors(graph, "ghost_id"), [])
        self.assertIsNone(find_path(graph, "ghost_1", "ghost_2"))

    # 23. CLI execution
    def test_23_cli_execution(self) -> None:
        self._create_sample_graph()
        inv_file = self.repo_path / "output" / "repository_inventory.json"
        ana_file = self.repo_path / "output" / "python_analysis.json"
        out_file = self.repo_path / "output" / "cli_graph.json"

        exit_code = main(
            [
                "--root",
                str(self.repo_path),
                "--inventory",
                str(inv_file),
                "--analysis",
                str(ana_file),
                "--output",
                str(out_file),
            ]
        )
        self.assertEqual(exit_code, 0)
        self.assertTrue(out_file.exists())

        with open(out_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["schema_version"], GRAPH_SCHEMA_VERSION)
        self.assertGreater(data["summary"]["node_count"], 0)


if __name__ == "__main__":
    unittest.main()
