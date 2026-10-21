"""Automated tests for JavaScript/TypeScript symbol resolution and multi-language graph integration."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from app.graph.graph_builder import (
    GRAPH_SCHEMA_VERSION,
    GraphBuilder,
    build_graph,
    main as builder_main,
)
from app.graph.graph_queries import (
    find_node_by_id,
    get_outgoing_neighbors,
)
from app.graph.models import (
    EDGE_TYPE_CALLS,
    EDGE_TYPE_DEFINES,
    EDGE_TYPE_IMPORTS,
    STATUS_AMBIGUOUS,
    STATUS_EXTERNAL,
    STATUS_UNRESOLVED,
)
from app.ingestion.scanner import scan_repository
from app.parsers.javascript_parser import (
    parse_js_repository_inventory,
)
from app.parsers.python_parser import (
    parse_repository_inventory as parse_py_inventory,
)


class TestMultiLanguageGraph(unittest.TestCase):
    """Test suite covering resolver and multi-language graph builder requirements."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo_path = Path(self.temp_dir.name).resolve()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    # 16. A local JavaScript import resolved to a file
    def test_16_local_javascript_import_resolved_to_file(self) -> None:
        (self.repo_path / "math.js").write_text(
            "export function add(a, b) { return a + b; }\n",
            encoding="utf-8",
        )
        (self.repo_path / "main.js").write_text(
            "import { add } from './math.js';\nadd(1, 2);\n",
            encoding="utf-8",
        )

        inv_file = self.repo_path / "inv.json"
        scan_repository(self.repo_path, output_path=inv_file)

        js_ana_file = self.repo_path / "js_ana.json"
        parse_js_repository_inventory(inv_file, self.repo_path, output_path=js_ana_file)

        graph = build_graph(self.repo_path, inv_file, js_ana_file)

        import_edges = [
            e for e in graph["edges"] if e["type"] == EDGE_TYPE_IMPORTS
        ]
        self.assertEqual(len(import_edges), 1)
        self.assertEqual(import_edges[0]["source"], "file:main.js")
        self.assertEqual(import_edges[0]["target"], "file:math.js")

    # 17. A local TypeScript import resolved to a file (extensionless and parent dir)
    def test_17_local_typescript_import_resolved_to_file(self) -> None:
        services_dir = self.repo_path / "services"
        services_dir.mkdir()
        (services_dir / "auth.ts").write_text(
            "export class AuthService {}\n",
            encoding="utf-8",
        )

        routes_dir = self.repo_path / "routes"
        routes_dir.mkdir()
        (routes_dir / "user.ts").write_text(
            "import { AuthService } from '../services/auth';\nnew AuthService();\n",
            encoding="utf-8",
        )

        inv_file = self.repo_path / "inv.json"
        scan_repository(self.repo_path, output_path=inv_file)

        js_ana_file = self.repo_path / "js_ana.json"
        parse_js_repository_inventory(inv_file, self.repo_path, output_path=js_ana_file)

        graph = build_graph(self.repo_path, inv_file, js_ana_file)

        import_edges = [
            e for e in graph["edges"] if e["type"] == EDGE_TYPE_IMPORTS
        ]
        self.assertEqual(len(import_edges), 1)
        self.assertEqual(import_edges[0]["source"], "file:routes/user.ts")
        self.assertEqual(import_edges[0]["target"], "file:services/auth.ts")

    # 18. An imported symbol connected to a unique exported definition
    def test_18_imported_symbol_connected_to_unique_exported_definition(self) -> None:
        (self.repo_path / "utils.js").write_text(
            "export function calculateTotal(price, qty) { return price * qty; }\n",
            encoding="utf-8",
        )
        (self.repo_path / "checkout.js").write_text(
            "import { calculateTotal } from './utils.js';\n"
            "function runCheckout() {\n"
            "  calculateTotal(10, 5);\n"
            "}\n",
            encoding="utf-8",
        )

        inv_file = self.repo_path / "inv.json"
        scan_repository(self.repo_path, output_path=inv_file)

        js_ana_file = self.repo_path / "js_ana.json"
        parse_js_repository_inventory(inv_file, self.repo_path, output_path=js_ana_file)

        graph = build_graph(self.repo_path, inv_file, js_ana_file)

        call_edges = [e for e in graph["edges"] if e["type"] == EDGE_TYPE_CALLS]
        self.assertEqual(len(call_edges), 1)
        self.assertTrue(call_edges[0]["source"].endswith("::runCheckout:function:2"))
        self.assertTrue(call_edges[0]["target"].endswith("::calculateTotal:function:1"))

    # 19. Named and aliased imports resolved correctly
    def test_19_named_and_aliased_imports_resolved_correctly(self) -> None:
        (self.repo_path / "calc.js").write_text(
            "export function multiply(a, b) { return a * b; }\n",
            encoding="utf-8",
        )
        (self.repo_path / "main.js").write_text(
            "import { multiply as mult } from './calc';\n"
            "mult(3, 4);\n",
            encoding="utf-8",
        )

        inv_file = self.repo_path / "inv.json"
        scan_repository(self.repo_path, output_path=inv_file)

        js_ana_file = self.repo_path / "js_ana.json"
        parse_js_repository_inventory(inv_file, self.repo_path, output_path=js_ana_file)

        graph = build_graph(self.repo_path, inv_file, js_ana_file)

        call_edges = [e for e in graph["edges"] if e["type"] == EDGE_TYPE_CALLS]
        self.assertEqual(len(call_edges), 1)
        self.assertEqual(call_edges[0]["metadata"]["strategy"], "imported_alias")
        self.assertTrue(call_edges[0]["target"].endswith("::multiply:function:1"))

    # 20. Namespace imports handled correctly for supported cases
    def test_20_namespace_imports_handled_correctly(self) -> None:
        (self.repo_path / "helpers.js").write_text(
            "export function formatDate(d) { return String(d); }\n",
            encoding="utf-8",
        )
        (self.repo_path / "view.js").write_text(
            "import * as helpers from './helpers';\n"
            "helpers.formatDate(123);\n",
            encoding="utf-8",
        )

        inv_file = self.repo_path / "inv.json"
        scan_repository(self.repo_path, output_path=inv_file)

        js_ana_file = self.repo_path / "js_ana.json"
        parse_js_repository_inventory(inv_file, self.repo_path, output_path=js_ana_file)

        graph = build_graph(self.repo_path, inv_file, js_ana_file)

        call_edges = [e for e in graph["edges"] if e["type"] == EDGE_TYPE_CALLS]
        self.assertEqual(len(call_edges), 1)
        self.assertEqual(call_edges[0]["metadata"]["strategy"], "namespace_call")
        self.assertTrue(call_edges[0]["target"].endswith("::formatDate:function:1"))

    # 21. this.method() resolved only when target is unambiguous
    def test_21_this_method_resolved_when_unambiguous(self) -> None:
        (self.repo_path / "order.js").write_text(
            "class OrderProcessor {\n"
            "  validate() { return true; }\n"
            "  process() {\n"
            "    this.validate();\n"
            "  }\n"
            "}\n",
            encoding="utf-8",
        )

        inv_file = self.repo_path / "inv.json"
        scan_repository(self.repo_path, output_path=inv_file)

        js_ana_file = self.repo_path / "js_ana.json"
        parse_js_repository_inventory(inv_file, self.repo_path, output_path=js_ana_file)

        graph = build_graph(self.repo_path, inv_file, js_ana_file)

        call_edges = [e for e in graph["edges"] if e["type"] == EDGE_TYPE_CALLS]
        self.assertEqual(len(call_edges), 1)
        self.assertEqual(call_edges[0]["metadata"]["strategy"], "this_method")
        self.assertTrue(call_edges[0]["source"].endswith("::OrderProcessor.process:method:3"))
        self.assertTrue(call_edges[0]["target"].endswith("::OrderProcessor.validate:method:2"))

    # 22. External packages do not become fake local nodes
    def test_22_external_packages_do_not_become_fake_local_nodes(self) -> None:
        (self.repo_path / "app.js").write_text(
            "import React from 'react';\n"
            "import express from 'express';\n"
            "console.log('started');\n"
            "fetch('/api');\n",
            encoding="utf-8",
        )

        inv_file = self.repo_path / "inv.json"
        scan_repository(self.repo_path, output_path=inv_file)

        js_ana_file = self.repo_path / "js_ana.json"
        parse_js_repository_inventory(inv_file, self.repo_path, output_path=js_ana_file)

        graph = build_graph(self.repo_path, inv_file, js_ana_file)

        node_ids = {n["id"] for n in graph["nodes"]}
        self.assertNotIn("file:react", node_ids)
        self.assertNotIn("file:express", node_ids)

        # External imports and calls tracked in diagnostics
        ext_refs = [
            u for u in graph["unresolved_references"] if u["status"] == STATUS_EXTERNAL
        ]
        self.assertGreater(len(ext_refs), 0)

    # 23. Duplicate symbol names remain distinct
    def test_23_duplicate_symbol_names_remain_distinct(self) -> None:
        (self.repo_path / "moduleA.js").write_text(
            "export function render() { return 'A'; }\n",
            encoding="utf-8",
        )
        (self.repo_path / "moduleB.js").write_text(
            "export function render() { return 'B'; }\n",
            encoding="utf-8",
        )

        inv_file = self.repo_path / "inv.json"
        scan_repository(self.repo_path, output_path=inv_file)

        js_ana_file = self.repo_path / "js_ana.json"
        parse_js_repository_inventory(inv_file, self.repo_path, output_path=js_ana_file)

        graph = build_graph(self.repo_path, inv_file, js_ana_file)

        render_nodes = [
            n for n in graph["nodes"] if n["name"] == "render"
        ]
        self.assertEqual(len(render_nodes), 2)
        self.assertNotEqual(render_nodes[0]["id"], render_nodes[1]["id"])

    # 24. Ambiguous and unresolved calls are represented correctly
    def test_24_ambiguous_and_unresolved_calls_represented_correctly(self) -> None:
        (self.repo_path / "a.js").write_text(
            "function executeTask() {}\n",
            encoding="utf-8",
        )
        (self.repo_path / "b.js").write_text(
            "function executeTask() {}\n",
            encoding="utf-8",
        )
        (self.repo_path / "caller.js").write_text(
            "executeTask();\n"
            "unknownHelper();\n",
            encoding="utf-8",
        )

        inv_file = self.repo_path / "inv.json"
        scan_repository(self.repo_path, output_path=inv_file)

        js_ana_file = self.repo_path / "js_ana.json"
        parse_js_repository_inventory(inv_file, self.repo_path, output_path=js_ana_file)

        graph = build_graph(self.repo_path, inv_file, js_ana_file)

        ambig_refs = [
            u for u in graph["unresolved_references"] if u["status"] == STATUS_AMBIGUOUS
        ]
        self.assertEqual(len(ambig_refs), 1)
        self.assertEqual(ambig_refs[0]["target_name"], "executeTask")
        self.assertEqual(len(ambig_refs[0]["candidates"]), 2)

        unresolved_refs = [
            u for u in graph["unresolved_references"] if u["status"] == STATUS_UNRESOLVED and u["kind"] == "call"
        ]
        self.assertTrue(any(u["target_name"] == "unknownHelper" for u in unresolved_refs))

    # 25. Unresolved references never produce fabricated confirmed edges
    def test_25_unresolved_references_never_produce_fabricated_edges(self) -> None:
        (self.repo_path / "orphan.js").write_text(
            "missingFunc();\n",
            encoding="utf-8",
        )
        inv_file = self.repo_path / "inv.json"
        scan_repository(self.repo_path, output_path=inv_file)

        js_ana_file = self.repo_path / "js_ana.json"
        parse_js_repository_inventory(inv_file, self.repo_path, output_path=js_ana_file)

        graph = build_graph(self.repo_path, inv_file, js_ana_file)

        call_edges = [e for e in graph["edges"] if e["type"] == EDGE_TYPE_CALLS]
        self.assertEqual(len(call_edges), 0)
        self.assertEqual(graph["summary"]["resolved_calls"], 0)
        self.assertEqual(graph["summary"]["unresolved_calls"], 1)

    # 26. Python-only graph generation continues to work
    def test_26_python_only_graph_generation_continues_to_work(self) -> None:
        (self.repo_path / "service.py").write_text(
            "def calculate(x: int) -> int:\n    return x * 2\n",
            encoding="utf-8",
        )
        (self.repo_path / "main.py").write_text(
            "import service\n\ndef main():\n    service.calculate(10)\n",
            encoding="utf-8",
        )

        inv_file = self.repo_path / "inv.json"
        scan_repository(self.repo_path, output_path=inv_file)

        py_ana_file = self.repo_path / "py_ana.json"
        parse_py_inventory(inv_file, self.repo_path, output_path=py_ana_file)

        graph = build_graph(self.repo_path, inv_file, py_ana_file)

        self.assertGreater(graph["summary"]["node_count"], 0)
        self.assertEqual(graph["summary"]["resolved_calls"], 1)
        self.assertEqual(graph["summary"]["resolved_imports"], 1)

    # 27. Combined Python and JavaScript/TypeScript analysis works
    def test_27_combined_python_and_javascript_typescript_analysis(self) -> None:
        backend_dir = self.repo_path / "backend"
        backend_dir.mkdir()
        (backend_dir / "api.py").write_text(
            "def get_user():\n    return {'name': 'Alice'}\n",
            encoding="utf-8",
        )

        frontend_dir = self.repo_path / "frontend"
        frontend_dir.mkdir()
        (frontend_dir / "types.ts").write_text(
            "export interface User {\n  name: string;\n}\n",
            encoding="utf-8",
        )
        (frontend_dir / "app.js").write_text(
            "function renderUser() {\n  return 'Alice';\n}\nrenderUser();\n",
            encoding="utf-8",
        )

        inv_file = self.repo_path / "inv.json"
        scan_repository(self.repo_path, output_path=inv_file)

        py_ana = self.repo_path / "py_ana.json"
        parse_py_inventory(inv_file, self.repo_path, output_path=py_ana)

        js_ana = self.repo_path / "js_ana.json"
        parse_js_repository_inventory(inv_file, self.repo_path, output_path=js_ana)

        # Build combined graph with multiple analysis files
        graph = build_graph(
            self.repo_path,
            inv_file,
            [py_ana, js_ana],
        )

        node_types = graph["summary"]["nodes_by_type"]
        self.assertIn("function", node_types)
        self.assertIn("interface", node_types)

        # Both Python and JS/TS files should be marked as analyzed
        file_nodes = {n["id"]: n for n in graph["nodes"] if n["type"] == "file"}
        self.assertTrue(file_nodes["file:backend/api.py"]["metadata"]["analyzed"])
        self.assertTrue(file_nodes["file:frontend/app.js"]["metadata"]["analyzed"])
        self.assertTrue(file_nodes["file:frontend/types.ts"]["metadata"]["analyzed"])

    # 28. Node and edge summary counts match serialized output
    def test_28_node_and_edge_summary_counts_match_output(self) -> None:
        (self.repo_path / "test.ts").write_text(
            "interface Config {}\nfunction run() {}\nrun();\n",
            encoding="utf-8",
        )
        inv_file = self.repo_path / "inv.json"
        scan_repository(self.repo_path, output_path=inv_file)
        js_ana = self.repo_path / "js_ana.json"
        parse_js_repository_inventory(inv_file, self.repo_path, output_path=js_ana)

        graph = build_graph(self.repo_path, inv_file, js_ana)

        summary = graph["summary"]
        self.assertEqual(summary["node_count"], len(graph["nodes"]))
        self.assertEqual(summary["edge_count"], len(graph["edges"]))
        self.assertEqual(
            sum(summary["nodes_by_type"].values()),
            len(graph["nodes"]),
        )
        self.assertEqual(
            sum(summary["edges_by_type"].values()),
            len(graph["edges"]),
        )

    # 29. Every edge endpoint exists
    def test_29_every_edge_endpoint_exists(self) -> None:
        (self.repo_path / "modA.js").write_text(
            "export function foo() {}\n", encoding="utf-8"
        )
        (self.repo_path / "modB.js").write_text(
            "import { foo } from './modA.js';\nfoo();\n", encoding="utf-8"
        )
        inv_file = self.repo_path / "inv.json"
        scan_repository(self.repo_path, output_path=inv_file)
        js_ana = self.repo_path / "js_ana.json"
        parse_js_repository_inventory(inv_file, self.repo_path, output_path=js_ana)

        graph = build_graph(self.repo_path, inv_file, js_ana)

        node_ids = {n["id"] for n in graph["nodes"]}
        for edge in graph["edges"]:
            self.assertIn(edge["source"], node_ids, f"Missing source: {edge['source']}")
            self.assertIn(edge["target"], node_ids, f"Missing target: {edge['target']}")

    # 30. Repeated builds produce deterministic output
    def test_30_repeated_builds_produce_deterministic_output(self) -> None:
        (self.repo_path / "a.js").write_text("function a() {}\n", encoding="utf-8")
        (self.repo_path / "b.ts").write_text("interface B {}\n", encoding="utf-8")
        inv_file = self.repo_path / "inv.json"
        scan_repository(self.repo_path, output_path=inv_file)
        js_ana = self.repo_path / "js_ana.json"
        parse_js_repository_inventory(inv_file, self.repo_path, output_path=js_ana)

        graph1 = build_graph(self.repo_path, inv_file, js_ana)
        graph2 = build_graph(self.repo_path, inv_file, js_ana)

        json1 = json.dumps(graph1, sort_keys=True)
        json2 = json.dumps(graph2, sort_keys=True)
        self.assertEqual(json1, json2)


if __name__ == "__main__":
    unittest.main()
