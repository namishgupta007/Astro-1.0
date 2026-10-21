"""Controlled graph-accuracy benchmark fixtures and evaluation harness.

Defines synthetic repositories with known expected symbols, imports, and call relationships
for Python and JavaScript/TypeScript codebases.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import tempfile
from typing import Any, Optional

from app.graph.graph_builder import build_graph
from app.graph.models import (
    EDGE_TYPE_CALLS,
    EDGE_TYPE_IMPORTS,
    STATUS_AMBIGUOUS,
    STATUS_EXTERNAL,
    STATUS_UNRESOLVED,
)
from app.ingestion.scanner import scan_repository
from app.parsers.javascript_parser import parse_js_repository_inventory
from app.parsers.python_parser import parse_repository_inventory as parse_py_inventory


@dataclass
class FixtureCase:
    """Represents a controlled benchmark case with known ground truth."""

    name: str
    language: str  # "python" or "javascript" / "typescript"
    description: str
    files: dict[str, str]
    # (caller_simple_or_qualified_name, callee_simple_or_qualified_name)
    expected_calls: list[tuple[str, str]] = field(default_factory=list)
    # Call pairs that MUST NOT be generated (e.g. shadowed names, unexported functions)
    forbidden_calls: list[tuple[str, str]] = field(default_factory=list)
    # (source_file_rel, target_file_rel)
    expected_imports: list[tuple[str, str]] = field(default_factory=list)
    # Expected unresolved references: list of dicts with keys e.g. status, target_name
    expected_unresolved: list[dict[str, Any]] = field(default_factory=list)
    # Dynamic or unsupported cases where calls are expected NOT to be resolved
    is_unresolvable_case: bool = False


@dataclass
class BenchmarkMetric:
    """Precision, recall, and F1 score calculation."""

    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0

    @property
    def precision(self) -> float:
        total = self.true_positives + self.false_positives
        return (self.true_positives / total) if total > 0 else 1.0

    @property
    def recall(self) -> float:
        total = self.true_positives + self.false_negatives
        return (self.true_positives / total) if total > 0 else 1.0

    @property
    def f1(self) -> float:
        p = self.precision
        r = self.recall
        return (2 * p * r / (p + r)) if (p + r) > 0 else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "tp": self.true_positives,
            "fp": self.false_positives,
            "fn": self.false_negatives,
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
        }


@dataclass
class FixtureEvaluationResult:
    """Result of running a benchmark case."""

    case_name: str
    language: str
    call_metrics: BenchmarkMetric
    import_metrics: BenchmarkMetric
    unresolved_count: int
    ambiguous_count: int
    external_count: int
    forbidden_call_violations: list[tuple[str, str]]
    predicted_calls: list[tuple[str, str]]
    expected_calls: list[tuple[str, str]]
    predicted_imports: list[tuple[str, str]]
    expected_imports: list[tuple[str, str]]
    passed: bool = True
    notes: list[str] = field(default_factory=list)


def get_python_fixtures() -> list[FixtureCase]:
    """16 required Python accuracy benchmark fixtures."""
    return [
        # 1. Direct call between two uniquely defined functions in the same module
        FixtureCase(
            name="py_01_direct_same_module",
            language="python",
            description="Direct call between two uniquely defined functions in the same module",
            files={
                "main.py": (
                    "def helper():\n"
                    "    return 42\n"
                    "\n"
                    "def run():\n"
                    "    return helper()\n"
                )
            },
            expected_calls=[("run", "helper")],
        ),
        # 2. Calls to imported functions from another module
        FixtureCase(
            name="py_02_imported_functions",
            language="python",
            description="Calls to imported functions from another module",
            files={
                "utils.py": (
                    "def compute(x):\n"
                    "    return x * 2\n"
                ),
                "main.py": (
                    "from utils import compute\n"
                    "\n"
                    "def execute():\n"
                    "    return compute(10)\n"
                ),
            },
            expected_calls=[("execute", "compute")],
            expected_imports=[("main.py", "utils.py")],
        ),
        # 3. Aliased imports
        FixtureCase(
            name="py_03_aliased_imports",
            language="python",
            description="Calls to functions imported with an alias",
            files={
                "math_ops.py": (
                    "def add(a, b):\n"
                    "    return a + b\n"
                ),
                "app.py": (
                    "from math_ops import add as sum_fn\n"
                    "\n"
                    "def calculate():\n"
                    "    return sum_fn(5, 7)\n"
                ),
            },
            expected_calls=[("calculate", "add")],
            expected_imports=[("app.py", "math_ops.py")],
        ),
        # 4. Relative imports within packages
        FixtureCase(
            name="py_04_relative_imports_pkg",
            language="python",
            description="Relative imports within packages (.sibling, ..parent)",
            files={
                "pkg/__init__.py": "# pkg root\n",
                "pkg/sibling.py": (
                    "def sibling_worker():\n"
                    "    return True\n"
                ),
                "pkg/consumer.py": (
                    "from .sibling import sibling_worker\n"
                    "\n"
                    "def run_consumer():\n"
                    "    return sibling_worker()\n"
                ),
            },
            expected_calls=[("run_consumer", "sibling_worker")],
            expected_imports=[("pkg/consumer.py", "pkg/sibling.py")],
        ),
        # 5. Calls between methods of the same class using self
        FixtureCase(
            name="py_05_self_methods",
            language="python",
            description="Calls between methods of the same class using self",
            files={
                "models.py": (
                    "class Worker:\n"
                    "    def step_one(self):\n"
                    "        return 1\n"
                    "    def do_work(self):\n"
                    "        return self.step_one()\n"
                )
            },
            expected_calls=[("Worker.do_work", "Worker.step_one")],
        ),
        # 6. Class methods called through cls where supported
        FixtureCase(
            name="py_06_cls_methods",
            language="python",
            description="Class methods called through cls",
            files={
                "factory.py": (
                    "class Builder:\n"
                    "    @classmethod\n"
                    "    def build_core(cls):\n"
                    "        return 'core'\n"
                    "    @classmethod\n"
                    "    def create(cls):\n"
                    "        return cls.build_core()\n"
                )
            },
            expected_calls=[("Builder.create", "Builder.build_core")],
        ),
        # 7. Class-qualified method calls
        FixtureCase(
            name="py_07_class_qualified_method",
            language="python",
            description="Class-qualified method call (ClassName.method())",
            files={
                "service.py": (
                    "class PaymentService:\n"
                    "    @staticmethod\n"
                    "    def validate():\n"
                    "        return True\n"
                    "\n"
                    "def checkout():\n"
                    "    return PaymentService.validate()\n"
                )
            },
            expected_calls=[("checkout", "PaymentService.validate")],
        ),
        # 8. Calls through imported module aliases
        FixtureCase(
            name="py_08_imported_module_alias",
            language="python",
            description="Calls through imported module aliases (import mod as m; m.func())",
            files={
                "helpers.py": (
                    "def perform_task():\n"
                    "    return 'done'\n"
                ),
                "main.py": (
                    "import helpers as h\n"
                    "\n"
                    "def main():\n"
                    "    return h.perform_task()\n"
                ),
            },
            expected_calls=[("main", "perform_task")],
            expected_imports=[("main.py", "helpers.py")],
        ),
        # 9. Nested functions with local scopes
        FixtureCase(
            name="py_09_nested_functions_scope",
            language="python",
            description="Nested functions with local scope - outer calls inner, module cannot see inner",
            files={
                "nested.py": (
                    "def outer():\n"
                    "    def inner():\n"
                    "        return 1\n"
                    "    return inner()\n"
                    "\n"
                    "def module_call():\n"
                    "    return outer()\n"
                )
            },
            expected_calls=[
                ("outer", "outer.inner"),
                ("module_call", "outer"),
            ],
            forbidden_calls=[
                ("module_call", "outer.inner"),
                ("file:nested.py", "outer.inner"),
            ],
        ),
        # 10. Functions with identical names in different modules
        FixtureCase(
            name="py_10_identical_names_diff_modules",
            language="python",
            description="Functions with identical names in different modules disambiguated by import",
            files={
                "mod_a.py": (
                    "def render():\n"
                    "    return 'A'\n"
                ),
                "mod_b.py": (
                    "def render():\n"
                    "    return 'B'\n"
                ),
                "caller.py": (
                    "from mod_a import render\n"
                    "\n"
                    "def execute():\n"
                    "    return render()\n"
                ),
            },
            expected_calls=[("execute", "render")],
            expected_imports=[("caller.py", "mod_a.py")],
        ),
        # 11. Local variable or parameter shadowing a global function name
        FixtureCase(
            name="py_11_shadowing_parameter_and_local",
            language="python",
            description="Local variable or parameter shadowing a global function name must NOT resolve to global",
            files={
                "shadow.py": (
                    "def process():\n"
                    "    return 'global process'\n"
                    "\n"
                    "def checkout(process):\n"
                    "    return process()\n"
                    "\n"
                    "def run_local():\n"
                    "    process = lambda: 'local'\n"
                    "    return process()\n"
                )
            },
            expected_calls=[],
            forbidden_calls=[
                ("checkout", "process"),
                ("run_local", "process"),
            ],
            expected_unresolved=[
                {"status": STATUS_UNRESOLVED, "target_name": "process"},
            ],
        ),
        # 12. Calls occurring at module level
        FixtureCase(
            name="py_12_module_level_calls",
            language="python",
            description="Calls occurring at module level (not inside any function)",
            files={
                "script.py": (
                    "def initialize():\n"
                    "    return True\n"
                    "\n"
                    "initialize()\n"
                )
            },
            expected_calls=[("file:script.py", "initialize")],
        ),
        # 13. Imported modules with __init__.py files
        FixtureCase(
            name="py_13_packages_with_init",
            language="python",
            description="Imported packages with __init__.py and submodules",
            files={
                "pkg/__init__.py": (
                    "from .core import run_core\n"
                ),
                "pkg/core.py": (
                    "def run_core():\n"
                    "    return 'core'\n"
                ),
                "main.py": (
                    "from pkg.core import run_core\n"
                    "\n"
                    "def start():\n"
                    "    return run_core()\n"
                ),
            },
            expected_calls=[("start", "run_core")],
            expected_imports=[
                ("main.py", "pkg/core.py"),
                ("pkg/__init__.py", "pkg/core.py"),
            ],
        ),
        # 14. Missing modules and external dependencies
        FixtureCase(
            name="py_14_missing_and_external",
            language="python",
            description="Missing modules and external dependencies produce no fake local nodes or confirmed edges",
            files={
                "ext.py": (
                    "import requests\n"
                    "import non_existent_library\n"
                    "\n"
                    "def fetch_data():\n"
                    "    return requests.get('https://example.com')\n"
                )
            },
            expected_calls=[],
            forbidden_calls=[("fetch_data", "get")],
            expected_unresolved=[
                {"status": STATUS_EXTERNAL, "target_name": "requests"},
                {"status": STATUS_EXTERNAL, "target_name": "non_existent_library"},
            ],
            is_unresolvable_case=True,
        ),
        # 15. Unresolvable dynamic calls
        FixtureCase(
            name="py_15_dynamic_calls",
            language="python",
            description="Unresolvable dynamic calls (getattr, dynamic dispatch, unknown object)",
            files={
                "dynamic.py": (
                    "def dispatch(handler, name):\n"
                    "    fn = getattr(handler, name)\n"
                    "    return fn()\n"
                )
            },
            expected_calls=[],
            is_unresolvable_case=True,
        ),
        # 16. Syntax errors that should not prevent other files from being analyzed
        FixtureCase(
            name="py_16_syntax_error_resilience",
            language="python",
            description="Syntax errors in one file do not prevent valid files from being analyzed",
            files={
                "broken.py": "def invalid_syntax(\n",
                "valid.py": (
                    "def working():\n"
                    "    return 1\n"
                    "\n"
                    "def runner():\n"
                    "    return working()\n"
                ),
            },
            expected_calls=[("runner", "working")],
        ),
    ]


def get_js_ts_fixtures() -> list[FixtureCase]:
    """17 required JavaScript/TypeScript accuracy benchmark fixtures."""
    return [
        # 1. Same-file function calls
        FixtureCase(
            name="js_01_same_file_call",
            language="javascript",
            description="Same-file function calls",
            files={
                "main.js": (
                    "function helper() {\n"
                    "    return 42;\n"
                    "}\n"
                    "function run() {\n"
                    "    return helper();\n"
                    "}\n"
                )
            },
            expected_calls=[("run", "helper")],
        ),
        # 2. Arrow functions referenced by name
        FixtureCase(
            name="js_02_arrow_function_call",
            language="javascript",
            description="Arrow functions assigned to const/let and referenced by name",
            files={
                "arrows.js": (
                    "const compute = (x) => x * 2;\n"
                    "function execute() {\n"
                    "    return compute(21);\n"
                    "}\n"
                )
            },
            expected_calls=[("execute", "compute")],
        ),
        # 3. Named imports
        FixtureCase(
            name="js_03_named_imports",
            language="javascript",
            description="Named imports from local module",
            files={
                "math.js": (
                    "export function add(a, b) {\n"
                    "    return a + b;\n"
                    "}\n"
                ),
                "main.js": (
                    "import { add } from './math.js';\n"
                    "function calc() {\n"
                    "    return add(1, 2);\n"
                    "}\n"
                ),
            },
            expected_calls=[("calc", "add")],
            expected_imports=[("main.js", "math.js")],
        ),
        # 4. Aliased imports
        FixtureCase(
            name="js_04_aliased_imports",
            language="javascript",
            description="Aliased imports (import { add as sum } from './math')",
            files={
                "math.js": (
                    "export function add(a, b) {\n"
                    "    return a + b;\n"
                    "}\n"
                ),
                "main.js": (
                    "import { add as sum } from './math.js';\n"
                    "function calc() {\n"
                    "    return sum(1, 2);\n"
                    "}\n"
                ),
            },
            expected_calls=[("calc", "add")],
            expected_imports=[("main.js", "math.js")],
        ),
        # 5. Namespace imports
        FixtureCase(
            name="js_05_namespace_imports",
            language="javascript",
            description="Namespace imports (import * as math from './math'; math.add())",
            files={
                "math.js": (
                    "export function add(a, b) {\n"
                    "    return a + b;\n"
                    "}\n"
                ),
                "main.js": (
                    "import * as math from './math.js';\n"
                    "function calc() {\n"
                    "    return math.add(1, 2);\n"
                    "}\n"
                ),
            },
            expected_calls=[("calc", "add")],
            expected_imports=[("main.js", "math.js")],
        ),
        # 6. Default imports and exports
        FixtureCase(
            name="js_06_default_import_export",
            language="javascript",
            description="Default export and default import",
            files={
                "service.js": (
                    "export default function Service() {\n"
                    "    return 'service';\n"
                    "}\n"
                ),
                "main.js": (
                    "import Service from './service.js';\n"
                    "function start() {\n"
                    "    return Service();\n"
                    "}\n"
                ),
            },
            expected_calls=[("start", "Service")],
            expected_imports=[("main.js", "service.js")],
        ),
        # 7. Re-export chains
        FixtureCase(
            name="js_07_reexport_chains",
            language="javascript",
            description="Re-export chains (export { fn } from './mod')",
            files={
                "core.js": (
                    "export function coreAction() {\n"
                    "    return 'core';\n"
                    "}\n"
                ),
                "reexporter.js": (
                    "export { coreAction } from './core.js';\n"
                ),
                "app.js": (
                    "import { coreAction } from './reexporter.js';\n"
                    "function run() {\n"
                    "    return coreAction();\n"
                    "}\n"
                ),
            },
            expected_calls=[("run", "coreAction")],
            expected_imports=[
                ("app.js", "reexporter.js"),
                ("reexporter.js", "core.js"),
            ],
        ),
        # 8. Local modules resolved through explicit extensions
        FixtureCase(
            name="js_08_explicit_extensions",
            language="typescript",
            description="Local modules resolved through explicit .ts/.js extensions",
            files={
                "utils.ts": (
                    "export function sanitize(s: string): string {\n"
                    "    return s.trim();\n"
                    "}\n"
                ),
                "app.ts": (
                    "import { sanitize } from './utils.js';\n"
                    "function process(input: string) {\n"
                    "    return sanitize(input);\n"
                    "}\n"
                ),
            },
            expected_calls=[("process", "sanitize")],
            expected_imports=[("app.ts", "utils.ts")],
        ),
        # 9. Extensionless imports and index files
        FixtureCase(
            name="js_09_extensionless_index",
            language="typescript",
            description="Extensionless imports and directory index files",
            files={
                "components/index.ts": (
                    "export function renderButton() {\n"
                    "    return 'button';\n"
                    "}\n"
                ),
                "app.ts": (
                    "import { renderButton } from './components';\n"
                    "function page() {\n"
                    "    return renderButton();\n"
                    "}\n"
                ),
            },
            expected_calls=[("page", "renderButton")],
            expected_imports=[("app.ts", "components/index.ts")],
        ),
        # 10. this.method() when the class context is unambiguous
        FixtureCase(
            name="js_10_this_method",
            language="javascript",
            description="this.method() calls inside class methods",
            files={
                "controller.js": (
                    "class Controller {\n"
                    "    log() {\n"
                    "        return 'log';\n"
                    "    }\n"
                    "    handle() {\n"
                    "        return this.log();\n"
                    "    }\n"
                    "}\n"
                )
            },
            expected_calls=[("Controller.handle", "Controller.log")],
        ),
        # 11. Constructor calls using new
        FixtureCase(
            name="js_11_constructor_call_new",
            language="javascript",
            description="Constructor calls using new ClassName()",
            files={
                "engine.js": (
                    "class Engine {\n"
                    "    constructor() {}\n"
                    "}\n"
                    "function start() {\n"
                    "    const e = new Engine();\n"
                    "    return e;\n"
                    "}\n"
                )
            },
            expected_calls=[("start", "Engine")],
        ),
        # 12. Same-named functions in different files
        FixtureCase(
            name="js_12_same_named_diff_files",
            language="javascript",
            description="Functions with identical names in different files",
            files={
                "moduleA.js": (
                    "export function render() {\n"
                    "    return 'A';\n"
                    "}\n"
                ),
                "moduleB.js": (
                    "export function render() {\n"
                    "    return 'B';\n"
                    "}\n"
                ),
                "caller.js": (
                    "import { render } from './moduleA.js';\n"
                    "function draw() {\n"
                    "    return render();\n"
                    "}\n"
                ),
            },
            expected_calls=[("draw", "render")],
            expected_imports=[("caller.js", "moduleA.js")],
        ),
        # 13. Local variables shadowing imported functions
        FixtureCase(
            name="js_13_shadowing_imported_function",
            language="javascript",
            description="Local parameter or variable shadowing imported function must NOT resolve to import",
            files={
                "payments.js": (
                    "export function validate() {\n"
                    "    return true;\n"
                    "}\n"
                ),
                "checkout.js": (
                    "import { validate } from './payments.js';\n"
                    "\n"
                    "function checkout(validate) {\n"
                    "    return validate();\n"
                    "}\n"
                    "\n"
                    "function process() {\n"
                    "    const validate = getValidator();\n"
                    "    return validate();\n"
                    "}\n"
                ),
            },
            expected_calls=[],
            forbidden_calls=[
                ("checkout", "validate"),
                ("process", "validate"),
            ],
            expected_imports=[("checkout.js", "payments.js")],
        ),
        # 14. External packages such as React or Express
        FixtureCase(
            name="js_14_external_packages",
            language="typescript",
            description="External packages (react, express) do not become fake local nodes or confirmed CALLS edges",
            files={
                "app.tsx": (
                    "import React, { useState } from 'react';\n"
                    "import express from 'express';\n"
                    "\n"
                    "function Component() {\n"
                    "    const [val, setVal] = useState(0);\n"
                    "    return val;\n"
                    "}\n"
                )
            },
            expected_calls=[],
            forbidden_calls=[("Component", "useState")],
            is_unresolvable_case=True,
        ),
        # 15. Unresolved dynamic member calls and computed property access
        FixtureCase(
            name="js_15_dynamic_member_calls",
            language="javascript",
            description="Dynamic member calls and computed property access remain unresolved without false positives",
            files={
                "dynamic.js": (
                    "function invokeDynamic(obj, key) {\n"
                    "    return obj[key]();\n"
                    "}\n"
                )
            },
            expected_calls=[],
            is_unresolvable_case=True,
        ),
        # 16. TypeScript declarations, interfaces, and types that should not be mistaken for executable functions
        FixtureCase(
            name="js_16_ts_types_and_interfaces",
            language="typescript",
            description="TypeScript types and interfaces are not mistaken for callable functions",
            files={
                "types.ts": (
                    "export interface Runner {\n"
                    "    run(): void;\n"
                    "}\n"
                    "export type Handler = () => void;\n"
                    "\n"
                    "export function realRunner() {\n"
                    "    return 'running';\n"
                    "}\n"
                    "\n"
                    "function execute() {\n"
                    "    return realRunner();\n"
                    "}\n"
                )
            },
            expected_calls=[("execute", "realRunner")],
            forbidden_calls=[
                ("execute", "Runner"),
                ("execute", "Handler"),
            ],
        ),
        # 17. Malformed source files and parser recovery
        FixtureCase(
            name="js_17_malformed_syntax_recovery",
            language="javascript",
            description="Parser recovers from malformed files and continues analyzing valid files",
            files={
                "broken.js": "function broken( { syntax error\n",
                "valid.js": (
                    "function helper() {\n"
                    "    return 1;\n"
                    "}\n"
                    "function caller() {\n"
                    "    return helper();\n"
                    "}\n"
                ),
            },
            expected_calls=[("caller", "helper")],
        ),
    ]


def evaluate_fixture(case: FixtureCase) -> FixtureEvaluationResult:
    """Execute a single benchmark case in an isolated temporary directory and evaluate accuracy."""
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_path = Path(temp_dir).resolve()

        # Write files
        for rel_path, content in case.files.items():
            full_path = repo_path / rel_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content, encoding="utf-8")

        inv_file = repo_path / "inv.json"
        scan_repository(repo_path, output_path=inv_file)

        analysis_files = []
        if case.language == "python" or any(f.endswith(".py") for f in case.files):
            py_ana = repo_path / "py_ana.json"
            parse_py_inventory(inv_file, repo_path, output_path=py_ana)
            analysis_files.append(py_ana)

        if case.language in ("javascript", "typescript") or any(
            f.endswith((".js", ".jsx", ".ts", ".tsx")) for f in case.files
        ):
            js_ana = repo_path / "js_ana.json"
            parse_js_repository_inventory(inv_file, repo_path, output_path=js_ana)
            analysis_files.append(js_ana)

        graph_dict = build_graph(repo_path, inv_file, analysis_files)

        nodes = {n["id"]: n for n in graph_dict["nodes"]}
        edges = graph_dict["edges"]
        unresolved = graph_dict.get("unresolved_references", [])

        # Extract predicted CALLS
        predicted_calls: list[tuple[str, str]] = []
        for e in edges:
            if e["type"] == EDGE_TYPE_CALLS:
                src_node = nodes.get(e["source"])
                tgt_node = nodes.get(e["target"])

                src_name = (
                    src_node["metadata"].get("qualified_name")
                    or src_node["name"]
                    if src_node
                    else e["source"]
                )
                tgt_name = (
                    tgt_node["metadata"].get("qualified_name")
                    or tgt_node["name"]
                    if tgt_node
                    else e["target"]
                )

                # For file-level calls, use "file:<filename>"
                if src_node and src_node["type"] == "file":
                    src_name = f"file:{src_node['name']}"

                predicted_calls.append((src_name, tgt_name))

        # Extract predicted IMPORTS
        predicted_imports: list[tuple[str, str]] = []
        for e in edges:
            if e["type"] == EDGE_TYPE_IMPORTS:
                src_node = nodes.get(e["source"])
                tgt_node = nodes.get(e["target"])
                src_path = src_node["metadata"].get("path") if src_node else e["source"]
                tgt_path = tgt_node["metadata"].get("path") if tgt_node else e["target"]
                predicted_imports.append((src_path, tgt_path))

        # Check call matches (allow simple or qualified matching)
        def call_matches(pred: tuple[str, str], exp: tuple[str, str]) -> bool:
            p_src, p_tgt = pred
            e_src, e_tgt = exp
            src_ok = (p_src == e_src) or (p_src.endswith(f".{e_src}")) or (e_src.endswith(f".{p_src}"))
            tgt_ok = (p_tgt == e_tgt) or (p_tgt.endswith(f".{e_tgt}")) or (e_tgt.endswith(f".{p_tgt}"))
            return src_ok and tgt_ok

        call_tp = 0
        call_fn = 0
        call_fp = 0

        matched_preds = set()
        for exp in case.expected_calls:
            matched = False
            for idx, pred in enumerate(predicted_calls):
                if call_matches(pred, exp):
                    matched = True
                    matched_preds.add(idx)
                    break
            if matched:
                call_tp += 1
            else:
                call_fn += 1

        for idx, pred in enumerate(predicted_calls):
            if idx not in matched_preds:
                # Any predicted call not in expected_calls is an extra prediction
                call_fp += 1

        # Check forbidden call violations explicitly
        forbidden_violations = []
        for forb in case.forbidden_calls:
            for pred in predicted_calls:
                if call_matches(pred, forb):
                    forbidden_violations.append(pred)

        # Import metrics
        imp_tp = 0
        imp_fn = 0
        imp_fp = 0
        matched_imp_preds = set()
        for exp in case.expected_imports:
            matched = False
            for idx, pred in enumerate(predicted_imports):
                if pred[0] == exp[0] and pred[1] == exp[1]:
                    matched = True
                    matched_imp_preds.add(idx)
                    break
            if matched:
                imp_tp += 1
            else:
                imp_fn += 1

        for idx, pred in enumerate(predicted_imports):
            if idx not in matched_imp_preds:
                imp_fp += 1

        call_metric = BenchmarkMetric(
            true_positives=call_tp,
            false_positives=call_fp,
            false_negatives=call_fn,
        )

        imp_metric = BenchmarkMetric(
            true_positives=imp_tp,
            false_positives=imp_fp,
            false_negatives=imp_fn,
        )

        unres_count = len([u for u in unresolved if u["status"] == STATUS_UNRESOLVED])
        ambig_count = len([u for u in unresolved if u["status"] == STATUS_AMBIGUOUS])
        ext_count = len([u for u in unresolved if u["status"] == STATUS_EXTERNAL])

        passed = (
            call_fn == 0
            and len(forbidden_violations) == 0
            and imp_fn == 0
        )

        notes = []
        if forbidden_violations:
            notes.append(f"Forbidden call violations detected: {forbidden_violations}")
        if call_fn > 0:
            notes.append(f"Missing {call_fn} expected calls")
        if call_fp > 0 and not forbidden_violations:
            notes.append(f"Extra {call_fp} predicted calls")
        if imp_fn > 0:
            notes.append(f"Missing {imp_fn} expected imports")

        return FixtureEvaluationResult(
            case_name=case.name,
            language=case.language,
            call_metrics=call_metric,
            import_metrics=imp_metric,
            unresolved_count=unres_count,
            ambiguous_count=ambig_count,
            external_count=ext_count,
            forbidden_call_violations=forbidden_violations,
            predicted_calls=predicted_calls,
            expected_calls=case.expected_calls,
            predicted_imports=predicted_imports,
            expected_imports=case.expected_imports,
            passed=passed,
            notes=notes,
        )


def run_benchmark_suite() -> dict[str, Any]:
    """Execute all Python and JS/TS benchmark cases and compute aggregate statistics."""
    py_cases = get_python_fixtures()
    js_cases = get_js_ts_fixtures()
    all_cases = py_cases + js_cases

    results: list[FixtureEvaluationResult] = []
    py_results: list[FixtureEvaluationResult] = []
    js_results: list[FixtureEvaluationResult] = []

    for c in all_cases:
        res = evaluate_fixture(c)
        results.append(res)
        if c.language == "python":
            py_results.append(res)
        else:
            js_results.append(res)

    def aggregate(subset: list[FixtureEvaluationResult]) -> dict[str, Any]:
        call_tp = sum(r.call_metrics.true_positives for r in subset)
        call_fp = sum(r.call_metrics.false_positives for r in subset)
        call_fn = sum(r.call_metrics.false_negatives for r in subset)
        imp_tp = sum(r.import_metrics.true_positives for r in subset)
        imp_fp = sum(r.import_metrics.false_positives for r in subset)
        imp_fn = sum(r.import_metrics.false_negatives for r in subset)

        total_call_m = BenchmarkMetric(call_tp, call_fp, call_fn)
        total_imp_m = BenchmarkMetric(imp_tp, imp_fp, imp_fn)
        total_rel_m = BenchmarkMetric(call_tp + imp_tp, call_fp + imp_fp, call_fn + imp_fn)

        passed_count = sum(1 for r in subset if r.passed)
        failed_count = len(subset) - passed_count

        return {
            "total_cases": len(subset),
            "passed_cases": passed_count,
            "failed_cases": failed_count,
            "calls": total_call_m.to_dict(),
            "imports": total_imp_m.to_dict(),
            "overall": total_rel_m.to_dict(),
            "total_unresolved": sum(r.unresolved_count for r in subset),
            "total_ambiguous": sum(r.ambiguous_count for r in subset),
            "total_external": sum(r.external_count for r in subset),
        }

    return {
        "python": aggregate(py_results),
        "javascript_typescript": aggregate(js_results),
        "total": aggregate(results),
        "details": [
            {
                "case": r.case_name,
                "language": r.language,
                "passed": r.passed,
                "call_metrics": r.call_metrics.to_dict(),
                "import_metrics": r.import_metrics.to_dict(),
                "violations": [f"{v[0]}->{v[1]}" for v in r.forbidden_call_violations],
                "notes": r.notes,
            }
            for r in results
        ],
    }
