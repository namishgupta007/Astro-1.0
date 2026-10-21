"""Automated unit and integration tests for Astral Cartographer's Python AST parser."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app.ingestion.scanner import scan_repository
from app.parsers.models import (
    Call,
    FileParseResult,
    Import,
    ParseError,
    ParseSummary,
    Symbol,
)
from app.parsers.python_parser import (
    SCHEMA_VERSION,
    PythonASTVisitor,
    main,
    parse_file_path,
    parse_repository,
    parse_repository_inventory,
    parse_source_file,
)


class TestPythonASTParser(unittest.TestCase):
    """Test suite covering all requirements and scenarios for the Python AST parser."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo_path = Path(self.temp_dir.name).resolve()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    # Scenario 1: A function with multiple parameters
    def test_01_function_with_multiple_parameters(self) -> None:
        code = (
            "def calculate(pos1, /, a, b=10, *args, kw_only=True, **kwargs) -> int:\n"
            "    return a + b\n"
        )
        res = parse_source_file(code, "calc.py")

        self.assertEqual(len(res.errors), 0)
        self.assertEqual(len(res.symbols), 1)

        sym = res.symbols[0]
        self.assertEqual(sym.name, "calculate")
        self.assertEqual(sym.qualified_name, "calculate")
        self.assertEqual(sym.kind, "function")
        self.assertEqual(sym.file_path, "calc.py")
        self.assertEqual(sym.lineno, 1)
        self.assertEqual(sym.end_lineno, 2)
        self.assertIsNone(sym.parent_scope)
        self.assertFalse(sym.is_async)

        expected_params = ["pos1", "a", "b", "*args", "kw_only", "**kwargs"]
        self.assertEqual(sym.parameters, expected_params)
        self.assertTrue(sym.signature.startswith("def calculate("))
        self.assertTrue("-> int" in sym.signature)
        self.assertTrue(sym.id.startswith("calc.py::calculate:function:1"))

    # Scenario 2: A class containing methods
    def test_02_class_containing_methods(self) -> None:
        code = (
            "@dataclass\n"
            "class UserService(BaseService, AuthMixin):\n"
            "    def __init__(self, db_client):\n"
            "        self.db = db_client\n"
            "\n"
            "    @classmethod\n"
            "    def create(cls):\n"
            "        return cls(None)\n"
            "\n"
            "    @staticmethod\n"
            "    def validate(email: str) -> bool:\n"
            "        return '@' in email\n"
            "\n"
            "    def get_user(self, user_id: int):\n"
            "        return self.db.find(user_id)\n"
        )
        res = parse_source_file(code, "service.py")

        self.assertEqual(len(res.errors), 0)
        symbols_by_name = {s.name: s for s in res.symbols}

        # Class checks
        self.assertIn("UserService", symbols_by_name)
        cls_sym = symbols_by_name["UserService"]
        self.assertEqual(cls_sym.kind, "class")
        self.assertEqual(cls_sym.qualified_name, "UserService")
        self.assertEqual(cls_sym.bases, ["BaseService", "AuthMixin"])
        self.assertEqual(cls_sym.decorators, ["@dataclass"])
        self.assertEqual(cls_sym.signature, "class UserService(BaseService, AuthMixin)")

        # Method checks
        for method_name in ["__init__", "create", "validate", "get_user"]:
            self.assertIn(method_name, symbols_by_name)
            m_sym = symbols_by_name[method_name]
            self.assertEqual(m_sym.kind, "method")
            self.assertEqual(m_sym.parent_scope, "UserService")
            self.assertEqual(m_sym.qualified_name, f"UserService.{method_name}")

        self.assertIn("@classmethod", symbols_by_name["create"].decorators)
        self.assertIn("@staticmethod", symbols_by_name["validate"].decorators)
        self.assertEqual(symbols_by_name["get_user"].parameters, ["self", "user_id"])

    # Scenario 3: Nested functions and scope tracking
    def test_03_nested_functions_and_scope_tracking(self) -> None:
        code = (
            "def outer_function(x):\n"
            "    def inner_helper(y):\n"
            "        def deeply_nested(z):\n"
            "            return x + y + z\n"
            "        return deeply_nested(y)\n"
            "    return inner_helper(x)\n"
        )
        res = parse_source_file(code, "nested.py")

        self.assertEqual(len(res.errors), 0)
        self.assertEqual(len(res.symbols), 3)

        outer = res.symbols[0]
        self.assertEqual(outer.name, "outer_function")
        self.assertEqual(outer.qualified_name, "outer_function")
        self.assertIsNone(outer.parent_scope)
        self.assertEqual(outer.kind, "function")

        inner = res.symbols[1]
        self.assertEqual(inner.name, "inner_helper")
        self.assertEqual(inner.qualified_name, "outer_function.inner_helper")
        self.assertEqual(inner.parent_scope, "outer_function")
        self.assertEqual(inner.kind, "function")

        deep = res.symbols[2]
        self.assertEqual(deep.name, "deeply_nested")
        self.assertEqual(deep.qualified_name, "outer_function.inner_helper.deeply_nested")
        self.assertEqual(deep.parent_scope, "outer_function.inner_helper")
        self.assertEqual(deep.kind, "function")

    # Scenario 4: Asynchronous functions
    def test_04_async_functions(self) -> None:
        code = (
            "async def fetch_metrics(endpoint: str, timeout: int = 30) -> dict:\n"
            "    return await client.get(endpoint)\n"
        )
        res = parse_source_file(code, "async_worker.py")

        self.assertEqual(len(res.errors), 0)
        self.assertEqual(len(res.symbols), 1)

        sym = res.symbols[0]
        self.assertEqual(sym.name, "fetch_metrics")
        self.assertEqual(sym.qualified_name, "fetch_metrics")
        self.assertEqual(sym.kind, "async_function")
        self.assertTrue(sym.is_async)
        self.assertEqual(sym.parameters, ["endpoint", "timeout"])
        self.assertTrue(sym.signature.startswith("async def fetch_metrics("))

    # Scenario 5: Plain imports and from imports with aliases
    def test_05_imports_with_and_without_aliases(self) -> None:
        code = (
            "import os, sys as system\n"
            "from pathlib import Path as P, PurePath\n"
            "from ..core.utils import helper as h\n"
            "from . import models\n"
            "from math import *\n"
        )
        res = parse_source_file(code, "importer.py")

        self.assertEqual(len(res.errors), 0)
        self.assertEqual(len(res.imports), 7)

        imp_dict = {(i.module, i.name): i for i in res.imports}

        # import os
        self.assertIn(("os", "os"), imp_dict)
        self.assertIsNone(imp_dict[("os", "os")].alias)
        self.assertEqual(imp_dict[("os", "os")].level, 0)

        # import sys as system
        self.assertIn(("system", "sys"), {(i.alias, i.name): i for i in res.imports})
        sys_imp = [i for i in res.imports if i.name == "sys"][0]
        self.assertEqual(sys_imp.alias, "system")

        # from pathlib import Path as P
        path_imp = [i for i in res.imports if i.name == "Path"][0]
        self.assertEqual(path_imp.module, "pathlib")
        self.assertEqual(path_imp.alias, "P")

        # from pathlib import PurePath
        pure_imp = [i for i in res.imports if i.name == "PurePath"][0]
        self.assertEqual(pure_imp.module, "pathlib")
        self.assertIsNone(pure_imp.alias)

        # from ..core.utils import helper as h
        h_imp = [i for i in res.imports if i.name == "helper"][0]
        self.assertEqual(h_imp.module, "core.utils")
        self.assertEqual(h_imp.alias, "h")
        self.assertEqual(h_imp.level, 2)

        # from . import models
        mod_imp = [i for i in res.imports if i.name == "models"][0]
        self.assertIsNone(mod_imp.module)
        self.assertEqual(mod_imp.level, 1)

        # from math import *
        star_imp = [i for i in res.imports if i.name == "*"][0]
        self.assertEqual(star_imp.module, "math")

    # Scenario 6: Calls to plain functions and attribute expressions
    def test_06_function_and_method_calls(self) -> None:
        code = (
            "module.helper()\n"
            "\n"
            "def run_process():\n"
            "    calculate_total()\n"
            "    service.process()\n"
            "    self.save()\n"
            "    client.get_subservice().execute()\n"
        )
        res = parse_source_file(code, "app.py")

        self.assertEqual(len(res.errors), 0)
        self.assertEqual(len(res.calls), 6)

        # Module-level call
        mod_call = res.calls[0]
        self.assertEqual(mod_call.callee, "module.helper")
        self.assertEqual(mod_call.callee_name, "helper")
        self.assertIsNone(mod_call.caller)
        self.assertTrue(mod_call.is_module_level)

        # Calls inside run_process
        inside_calls = res.calls[1:]
        for c in inside_calls:
            self.assertEqual(c.caller, "run_process")
            self.assertFalse(c.is_module_level)
            self.assertTrue("app.py::run_process:function:" in c.caller_symbol_id)

        callees = [c.callee for c in inside_calls]
        callee_names = [c.callee_name for c in inside_calls]

        self.assertIn("calculate_total", callees)
        self.assertIn("service.process", callees)
        self.assertIn("self.save", callees)
        self.assertIn("client.get_subservice().execute", callees)

        self.assertIn("calculate_total", callee_names)
        self.assertIn("process", callee_names)
        self.assertIn("save", callee_names)
        self.assertIn("execute", callee_names)

    # Scenario 7: Accurate source-line locations
    def test_07_source_line_accuracy(self) -> None:
        code = (
            "# Line 1\n"
            "import os\n"  # Line 2
            "\n"  # Line 3
            "def first_function():\n"  # Line 4
            "    x = 1\n"  # Line 5
            "    return x\n"  # Line 6
            "\n"  # Line 7
            "class MyClass:\n"  # Line 8
            "    def method(self):\n"  # Line 9
            "        pass\n"  # Line 10
        )
        res = parse_source_file(code, "test_lines.py")

        self.assertEqual(res.imports[0].lineno, 2)

        func_sym = [s for s in res.symbols if s.name == "first_function"][0]
        self.assertEqual(func_sym.lineno, 4)
        self.assertEqual(func_sym.end_lineno, 6)
        self.assertEqual(func_sym.col_offset, 0)

        cls_sym = [s for s in res.symbols if s.name == "MyClass"][0]
        self.assertEqual(cls_sym.lineno, 8)
        self.assertEqual(cls_sym.end_lineno, 10)

        meth_sym = [s for s in res.symbols if s.name == "method"][0]
        self.assertEqual(meth_sym.lineno, 9)
        self.assertEqual(meth_sym.end_lineno, 10)
        self.assertEqual(meth_sym.col_offset, 4)

    # Scenario 8: Malformed Python syntax and graceful error handling
    def test_08_malformed_syntax_handled_gracefully(self) -> None:
        valid_file = self.repo_path / "valid.py"
        valid_file.write_text("def ok():\n    pass\n", encoding="utf-8")

        broken_file = self.repo_path / "broken.py"
        broken_file.write_text("def broken(:\n    print 'syntax error'\n", encoding="utf-8")

        res_broken = parse_file_path(broken_file, self.repo_path)
        self.assertEqual(len(res_broken.errors), 1)
        self.assertEqual(len(res_broken.symbols), 0)
        self.assertEqual(res_broken.errors[0].file_path, "broken.py")
        self.assertIsNotNone(res_broken.errors[0].lineno)
        self.assertTrue("SyntaxError" in res_broken.errors[0].error_message)

        # Both analyzed together
        inv = scan_repository(self.repo_path)
        inv_file = self.repo_path / "inventory.json"
        with open(inv_file, "w", encoding="utf-8") as f:
            json.dump(inv, f)

        analysis = parse_repository_inventory(inv_file, self.repo_path)
        self.assertEqual(analysis["summary"]["python_files_discovered"], 2)
        self.assertEqual(analysis["summary"]["python_files_parsed"], 1)
        self.assertEqual(analysis["summary"]["python_files_with_errors"], 1)
        self.assertEqual(len(analysis["symbols"]), 1)
        self.assertEqual(len(analysis["parse_errors"]), 1)

    # Scenario 9: Empty repositories and repositories without Python files
    def test_09_empty_and_non_python_repositories(self) -> None:
        # Non-Python files only
        (self.repo_path / "README.md").write_text("# Notes", encoding="utf-8")
        (self.repo_path / "style.css").write_text("body {}", encoding="utf-8")

        inv = scan_repository(self.repo_path)
        inv_file = self.repo_path / "inventory.json"
        with open(inv_file, "w", encoding="utf-8") as f:
            json.dump(inv, f)

        analysis = parse_repository_inventory(inv_file, self.repo_path)
        self.assertEqual(analysis["summary"]["python_files_discovered"], 0)
        self.assertEqual(analysis["summary"]["python_files_parsed"], 0)
        self.assertEqual(analysis["summary"]["symbols_found"], 0)
        self.assertEqual(analysis["symbols"], [])
        self.assertEqual(analysis["imports"], [])
        self.assertEqual(analysis["calls"], [])
        self.assertEqual(analysis["parse_errors"], [])

    # Scenario 10: Stable output and symbol IDs between repeated runs
    def test_10_deterministic_output_and_symbol_ids(self) -> None:
        (self.repo_path / "b_module.py").write_text(
            "def worker():\n    return 1\n", encoding="utf-8"
        )
        (self.repo_path / "a_module.py").write_text(
            "class Alpha:\n    def execute(self):\n        return 2\n", encoding="utf-8"
        )

        inv = scan_repository(self.repo_path)
        inv_file = self.repo_path / "inventory.json"
        with open(inv_file, "w", encoding="utf-8") as f:
            json.dump(inv, f)

        run1 = parse_repository_inventory(inv_file, self.repo_path)
        run2 = parse_repository_inventory(inv_file, self.repo_path)

        # Assert symbol IDs match and are deterministic
        ids1 = [s["id"] for s in run1["symbols"]]
        ids2 = [s["id"] for s in run2["symbols"]]
        self.assertEqual(ids1, ids2)

        # Full JSON comparison
        self.assertEqual(json.dumps(run1, sort_keys=True), json.dumps(run2, sort_keys=True))

    # Scenario 11: File paths outside repository and symbolic links rejected safely
    def test_11_paths_outside_repository_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as outside_dir:
            outside_path = Path(outside_dir)
            outside_file = outside_path / "secret.py"
            outside_file.write_text("def secret(): pass", encoding="utf-8")

            # Test escaping path via relative traversal
            escaping_res = parse_file_path(
                file_path=outside_file,
                repo_root=self.repo_path,
            )
            self.assertEqual(len(escaping_res.errors), 1)
            self.assertTrue("escapes repository root" in escaping_res.errors[0].error_message)

            # Test symlink pointing outside repository
            symlink_file = self.repo_path / "link_secret.py"
            try:
                os.symlink(outside_file, symlink_file)
                symlink_created = True
            except (OSError, NotImplementedError):
                symlink_created = False

            if symlink_created:
                symlink_res = parse_file_path(symlink_file, self.repo_path)
                self.assertEqual(len(symlink_res.errors), 1)
                self.assertTrue("Symbolic link" in symlink_res.errors[0].error_message)

    # Scenario 12: Integration with existing scanner inventory
    def test_12_integration_with_scanner_inventory(self) -> None:
        # Create a realistic project structure
        (self.repo_path / "main.py").write_text("import app\napp.start()\n", encoding="utf-8")
        src = self.repo_path / "pkg"
        src.mkdir()
        (src / "app.py").write_text("def start():\n    print('started')\n", encoding="utf-8")
        (src / "README.md").write_text("# Doc", encoding="utf-8")
        (self.repo_path / ".env").write_text("SECRET=123", encoding="utf-8")

        # Step 1: Scan repository
        inv_file = self.repo_path / "output" / "repository_inventory.json"
        inv = scan_repository(self.repo_path, output_path=inv_file)

        # Step 2: Parse using Step 1 inventory
        analysis_file = self.repo_path / "output" / "python_analysis.json"
        analysis = parse_repository_inventory(
            inventory_path=inv_file,
            repo_root=self.repo_path,
            output_path=analysis_file,
        )

        self.assertTrue(analysis_file.exists())
        self.assertEqual(analysis["summary"]["python_files_discovered"], 2)
        self.assertEqual(analysis["summary"]["python_files_parsed"], 2)
        self.assertEqual(analysis["summary"]["python_files_with_errors"], 0)

        # Ensure Markdown and sensitive .env files were never parsed
        parsed_paths = [s["file_path"] for s in analysis["symbols"]] + [
            i["file_path"] for i in analysis["imports"]
        ]
        self.assertFalse(any("README.md" in p for p in parsed_paths))
        self.assertFalse(any(".env" in p for p in parsed_paths))

    # Scenario 13: The parser never executes analyzed source code
    def test_13_parser_never_executes_analyzed_code(self) -> None:
        canary_file = self.repo_path / "canary.txt"
        canary_file.write_text("alive", encoding="utf-8")

        malicious_code = (
            "import os, sys\n"
            f"if os.path.exists({repr(str(canary_file))}):\n"
            f"    os.remove({repr(str(canary_file))})\n"
            "raise SystemExit(99)\n"
        )
        malicious_py = self.repo_path / "danger.py"
        malicious_py.write_text(malicious_code, encoding="utf-8")

        # Parse source and file
        res1 = parse_source_file(malicious_code, "danger.py")
        res2 = parse_file_path(malicious_py, self.repo_path)

        # Verify canary was not removed
        self.assertTrue(canary_file.exists())
        self.assertEqual(canary_file.read_text(encoding="utf-8"), "alive")

        # Verify calls were safely inspected via AST without execution
        callees = [c.callee for c in res1.calls]
        self.assertIn("os.path.exists", callees)
        self.assertIn("os.remove", callees)

    # Scenario 14: The CLI generates valid JSON with correct summary counts
    def test_14_cli_execution_and_summary_counts(self) -> None:
        (self.repo_path / "script.py").write_text(
            "import math\n\ndef square(x: float) -> float:\n    return math.pow(x, 2)\n",
            encoding="utf-8",
        )
        inv_file = self.repo_path / "inv.json"
        scan_repository(self.repo_path, output_path=inv_file)

        out_file = self.repo_path / "out_analysis.json"
        exit_code = main(
            [
                "--root",
                str(self.repo_path),
                "--inventory",
                str(inv_file),
                "--output",
                str(out_file),
            ]
        )
        self.assertEqual(exit_code, 0)
        self.assertTrue(out_file.exists())

        with open(out_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertEqual(data["schema_version"], SCHEMA_VERSION)
        self.assertEqual(data["summary"]["python_files_discovered"], 1)
        self.assertEqual(data["summary"]["python_files_parsed"], 1)
        self.assertEqual(data["summary"]["symbols_found"], 1)
        self.assertEqual(data["summary"]["imports_found"], 1)
        self.assertEqual(data["summary"]["calls_found"], 1)


if __name__ == "__main__":
    unittest.main()
