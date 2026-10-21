"""Automated unit and integration tests for Astral Cartographer's JavaScript/TypeScript parser."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest

from app.ingestion.scanner import scan_repository
from app.parsers.javascript_parser import (
    SCHEMA_VERSION,
    main,
    parse_js_file_path,
    parse_js_repository,
    parse_js_repository_inventory,
    parse_js_source_code,
)
from app.parsers.models import (
    Call,
    Export,
    FileParseResult,
    Import,
    JSParseSummary,
    ParseError,
    Symbol,
)


class TestJavaScriptParser(unittest.TestCase):
    """Test suite covering JavaScript and TypeScript Tree-sitter AST extraction."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo_path = Path(self.temp_dir.name).resolve()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    # 1. JavaScript function declarations
    def test_01_function_declarations(self) -> None:
        code = "function checkout(orderId, amount) {\n  return amount > 0;\n}\n"
        res = parse_js_source_code(code, "checkout.js")

        self.assertEqual(len(res.errors), 0)
        self.assertEqual(len(res.symbols), 1)
        sym = res.symbols[0]
        self.assertEqual(sym.name, "checkout")
        self.assertEqual(sym.qualified_name, "checkout")
        self.assertEqual(sym.kind, "function")
        self.assertEqual(sym.file_path, "checkout.js")
        self.assertEqual(sym.lineno, 1)
        self.assertEqual(sym.end_lineno, 3)
        self.assertFalse(sym.is_async)
        self.assertEqual(sym.parameters, ["orderId", "amount"])
        self.assertEqual(sym.signature, "function checkout(orderId, amount)")
        self.assertTrue(sym.id.startswith("checkout.js::checkout:function:1"))

    # 2. Async functions and arrow functions
    def test_02_async_and_arrow_functions(self) -> None:
        code = (
            "async function fetchOrders() {\n"
            "  return [];\n"
            "}\n"
            "const calculateTotal = (price, quantity) => price * quantity;\n"
            "const double = x => x * 2;\n"
        )
        res = parse_js_source_code(code, "orders.js")

        self.assertEqual(len(res.errors), 0)
        symbols_by_name = {s.name: s for s in res.symbols}

        self.assertIn("fetchOrders", symbols_by_name)
        async_sym = symbols_by_name["fetchOrders"]
        self.assertEqual(async_sym.kind, "async_function")
        self.assertTrue(async_sym.is_async)
        self.assertEqual(async_sym.parameters, [])
        self.assertEqual(async_sym.signature, "async function fetchOrders()")

        self.assertIn("calculateTotal", symbols_by_name)
        arrow_sym = symbols_by_name["calculateTotal"]
        self.assertEqual(arrow_sym.kind, "function")
        self.assertEqual(arrow_sym.parameters, ["price", "quantity"])
        self.assertTrue(arrow_sym.signature.startswith("const calculateTotal = (price, quantity) =>"))

        self.assertIn("double", symbols_by_name)
        single_param_sym = symbols_by_name["double"]
        self.assertEqual(single_param_sym.parameters, ["x"])

    # 3. Function expressions assigned to variables
    def test_03_function_expressions_assigned_to_variables(self) -> None:
        code = (
            "const validate = function(value) {\n"
            "  return Boolean(value);\n"
            "};\n"
            "const process = async function namedProc(item) {\n"
            "  return item;\n"
            "};\n"
            "const nonFunction = 42;\n"
        )
        res = parse_js_source_code(code, "validate.js")

        self.assertEqual(len(res.errors), 0)
        symbols_by_name = {s.name: s for s in res.symbols}

        self.assertIn("validate", symbols_by_name)
        val_sym = symbols_by_name["validate"]
        self.assertEqual(val_sym.kind, "function")
        self.assertEqual(val_sym.parameters, ["value"])

        self.assertIn("process", symbols_by_name)
        proc_sym = symbols_by_name["process"]
        self.assertEqual(proc_sym.kind, "async_function")
        self.assertTrue(proc_sym.is_async)
        self.assertEqual(proc_sym.parameters, ["item"])

        # Non-function variables must not be extracted as function symbols
        self.assertNotIn("nonFunction", symbols_by_name)

    # 4. Classes, methods, and constructors
    def test_04_classes_methods_and_constructors(self) -> None:
        code = (
            "class PaymentService extends BaseService {\n"
            "  constructor(config) {\n"
            "    this.config = config;\n"
            "  }\n"
            "  validatePayment(payment) {\n"
            "    return true;\n"
            "  }\n"
            "  async processPayment(payment) {\n"
            "    return this.validatePayment(payment);\n"
            "  }\n"
            "}\n"
        )
        res = parse_js_source_code(code, "services/payment.js")

        self.assertEqual(len(res.errors), 0)
        symbols_by_name = {s.name: s for s in res.symbols}

        self.assertIn("PaymentService", symbols_by_name)
        cls_sym = symbols_by_name["PaymentService"]
        self.assertEqual(cls_sym.kind, "class")
        self.assertEqual(cls_sym.bases, ["BaseService"])
        self.assertEqual(cls_sym.signature, "class PaymentService extends BaseService")

        self.assertIn("constructor", symbols_by_name)
        ctor_sym = symbols_by_name["constructor"]
        self.assertEqual(ctor_sym.kind, "method")
        self.assertEqual(ctor_sym.parent_scope, "PaymentService")
        self.assertEqual(ctor_sym.qualified_name, "PaymentService.constructor")
        self.assertEqual(ctor_sym.parameters, ["config"])

        self.assertIn("validatePayment", symbols_by_name)
        meth_sym = symbols_by_name["validatePayment"]
        self.assertEqual(meth_sym.kind, "method")
        self.assertEqual(meth_sym.qualified_name, "PaymentService.validatePayment")
        self.assertFalse(meth_sym.is_async)

        self.assertIn("processPayment", symbols_by_name)
        async_meth = symbols_by_name["processPayment"]
        self.assertEqual(async_meth.kind, "method")
        self.assertTrue(async_meth.is_async)

    # 5. Imports with default, named, namespace, and aliased forms
    def test_05_imports_all_forms(self) -> None:
        code = (
            "import React from 'react';\n"
            "import { useState, useEffect as useEff } from 'react';\n"
            "import * as utilities from './utilities.js';\n"
            "import './styles.css';\n"
        )
        res = parse_js_source_code(code, "app.js")

        self.assertEqual(len(res.errors), 0)
        self.assertEqual(len(res.imports), 5)

        # Default import
        def_imp = next(i for i in res.imports if i.alias == "React")
        self.assertEqual(def_imp.module, "react")
        self.assertEqual(def_imp.name, "default")
        self.assertEqual(def_imp.import_form, "default")

        # Named import
        named_imp = next(i for i in res.imports if i.name == "useState")
        self.assertEqual(named_imp.module, "react")
        self.assertIsNone(named_imp.alias)
        self.assertEqual(named_imp.import_form, "named")

        # Aliased named import
        alias_imp = next(i for i in res.imports if i.alias == "useEff")
        self.assertEqual(alias_imp.name, "useEffect")
        self.assertEqual(alias_imp.module, "react")
        self.assertEqual(alias_imp.import_form, "named")

        # Namespace import
        ns_imp = next(i for i in res.imports if i.import_form == "namespace")
        self.assertEqual(ns_imp.module, "./utilities.js")
        self.assertEqual(ns_imp.name, "*")
        self.assertEqual(ns_imp.alias, "utilities")

        # Side-effect import
        side_imp = next(i for i in res.imports if i.import_form == "side_effect")
        self.assertEqual(side_imp.module, "./styles.css")
        self.assertEqual(side_imp.name, "")

    # 6. Re-exports and default exports
    def test_06_reexports_and_default_exports(self) -> None:
        code = (
            "export { checkout, validate as checkValid } from './payments.js';\n"
            "export * from './utilities.js';\n"
            "export * as helpers from './helpers.js';\n"
            "export default class MainApp {}\n"
            "export const version = '1.0.0';\n"
        )
        res = parse_js_source_code(code, "index.js")

        self.assertEqual(len(res.errors), 0)
        exp_by_name = {e.name: e for e in res.exports}

        self.assertIn("checkout", exp_by_name)
        self.assertTrue(exp_by_name["checkout"].is_reexport)
        self.assertEqual(exp_by_name["checkout"].source_module, "./payments.js")

        self.assertIn("checkValid", exp_by_name)
        self.assertEqual(exp_by_name["checkValid"].alias, "validate")
        self.assertEqual(exp_by_name["checkValid"].source_module, "./payments.js")

        self.assertIn("*", exp_by_name)
        self.assertTrue(exp_by_name["*"].is_reexport)
        self.assertEqual(exp_by_name["*"].source_module, "./utilities.js")

        self.assertIn("helpers", exp_by_name)
        self.assertTrue(exp_by_name["helpers"].is_reexport)

        self.assertIn("default", exp_by_name)
        self.assertTrue(exp_by_name["default"].is_default)

    # 7. Type-only imports and exported TypeScript declarations
    def test_07_type_only_imports_and_declarations(self) -> None:
        code = (
            "import type { Payment, TransactionId } from './types.ts';\n"
            "export type { Payment };\n"
            "export interface UserProfile {\n"
            "  id: string;\n"
            "}\n"
        )
        res = parse_js_source_code(code, "profile.ts")

        self.assertEqual(len(res.errors), 0)
        self.assertEqual(len(res.imports), 2)
        for imp in res.imports:
            self.assertTrue(imp.is_type_only)
            self.assertEqual(imp.import_form, "type_only")

        self.assertTrue(any(e.is_type_only for e in res.exports))
        profile_sym = next(s for s in res.symbols if s.name == "UserProfile")
        self.assertTrue(profile_sym.is_exported)

    # 8. Interfaces, type aliases, and enums
    def test_08_interfaces_type_aliases_enums(self) -> None:
        code = (
            "interface OrderItem extends BaseItem {\n"
            "  quantity: number;\n"
            "}\n"
            "type OrderStatus = 'pending' | 'shipped' | 'delivered';\n"
            "enum Role {\n"
            "  Admin = 'ADMIN',\n"
            "  User = 'USER',\n"
            "}\n"
        )
        res = parse_js_source_code(code, "models.ts")

        self.assertEqual(len(res.errors), 0)
        syms = {s.name: s for s in res.symbols}

        self.assertIn("OrderItem", syms)
        self.assertEqual(syms["OrderItem"].kind, "interface")
        self.assertEqual(syms["OrderItem"].bases, ["BaseItem"])
        self.assertEqual(syms["OrderItem"].signature, "interface OrderItem extends BaseItem")

        self.assertIn("OrderStatus", syms)
        self.assertEqual(syms["OrderStatus"].kind, "type_alias")
        self.assertTrue("pending" in syms["OrderStatus"].signature)

        self.assertIn("Role", syms)
        self.assertEqual(syms["Role"].kind, "enum")
        self.assertEqual(syms["Role"].signature, "enum Role")

    # 9. Calls, member calls, and constructor invocations
    def test_09_calls_member_calls_and_constructors(self) -> None:
        code = (
            "checkout();\n"
            "paymentService.validatePayment();\n"
            "utilities.calculateTotal(10, 2);\n"
            "const service = new PaymentService();\n"
            "function process() {\n"
            "  service.validatePayment();\n"
            "}\n"
        )
        res = parse_js_source_code(code, "main.js")

        self.assertEqual(len(res.errors), 0)
        self.assertEqual(len(res.calls), 5)

        # Plain call
        c0 = res.calls[0]
        self.assertEqual(c0.callee, "checkout")
        self.assertEqual(c0.callee_name, "checkout")
        self.assertEqual(c0.call_kind, "function_call")
        self.assertTrue(c0.is_module_level)

        # Member call
        c1 = res.calls[1]
        self.assertEqual(c1.callee, "paymentService.validatePayment")
        self.assertEqual(c1.callee_name, "validatePayment")
        self.assertEqual(c1.call_kind, "method_call")

        # Constructor call
        c3 = res.calls[3]
        self.assertEqual(c3.callee, "new PaymentService")
        self.assertEqual(c3.callee_name, "PaymentService")
        self.assertEqual(c3.call_kind, "constructor_call")

        # Nested call inside function
        c4 = res.calls[4]
        self.assertFalse(c4.is_module_level)
        self.assertEqual(c4.caller, "process")

    # 10. Accurate source positions and qualified names
    def test_10_source_positions_and_qualified_names(self) -> None:
        code = (
            "// Line 1\n"
            "class MathUtils {\n"
            "  static add(a, b) {\n"
            "    return a + b;\n"
            "  }\n"
            "}\n"
        )
        res = parse_js_source_code(code, "math.js")

        self.assertEqual(len(res.errors), 0)
        cls_sym = next(s for s in res.symbols if s.name == "MathUtils")
        self.assertEqual(cls_sym.lineno, 2)
        self.assertEqual(cls_sym.col_offset, 0)
        self.assertEqual(cls_sym.end_lineno, 6)

        meth_sym = next(s for s in res.symbols if s.name == "add")
        self.assertEqual(meth_sym.lineno, 3)
        self.assertEqual(meth_sym.qualified_name, "MathUtils.add")

    # 11. Malformed syntax and parser recovery
    def test_11_malformed_syntax_and_parser_recovery(self) -> None:
        code = (
            "function broken() {\n"
            "  const x = ;\n"
            "}\n"
            "function healthy() {\n"
            "  return 42;\n"
            "}\n"
        )
        res = parse_js_source_code(code, "broken.js")

        # Errors detected
        self.assertGreater(len(res.errors), 0)
        self.assertEqual(res.errors[0].file_path, "broken.js")
        self.assertIsNotNone(res.errors[0].lineno)

        # Healthy function recovered and extracted
        healthy = next((s for s in res.symbols if s.name == "healthy"), None)
        self.assertIsNotNone(healthy)
        self.assertEqual(healthy.kind, "function")

    # 12. Stable IDs and output ordering
    def test_12_stable_ids_and_output_ordering(self) -> None:
        code = "function b() {}\nfunction a() {}\n"
        res1 = parse_js_source_code(code, "test.js")
        res2 = parse_js_source_code(code, "test.js")

        self.assertEqual([s.id for s in res1.symbols], [s.id for s in res2.symbols])
        self.assertEqual(res1.symbols[0].id, "test.js::b:function:1")
        self.assertEqual(res1.symbols[1].id, "test.js::a:function:2")

    # 13. Empty repositories and files with no declarations
    def test_13_empty_files_and_repositories(self) -> None:
        # File with only comments and blank lines
        code = "// Just a comment\n\n/* block comment */\n"
        res = parse_js_source_code(code, "empty.js")

        self.assertEqual(len(res.errors), 0)
        self.assertEqual(len(res.symbols), 0)
        self.assertEqual(len(res.imports), 0)
        self.assertEqual(len(res.exports), 0)
        self.assertEqual(len(res.calls), 0)

        # Empty repository run
        inv_file = self.repo_path / "inv.json"
        with open(inv_file, "w", encoding="utf-8") as f:
            json.dump({"schema_version": 1, "repository_name": "empty", "files": []}, f)

        analysis = parse_js_repository_inventory(inv_file, self.repo_path)
        self.assertEqual(analysis["summary"]["javascript_files_discovered"], 0)
        self.assertEqual(analysis["summary"]["symbols_found"], 0)

    # 14. Out-of-root paths and symlinks rejected safely
    def test_14_paths_outside_root_and_symlinks_rejected(self) -> None:
        outside_file = Path(tempfile.gettempdir()) / "outside.js"
        outside_file.write_text("function secret() {}", encoding="utf-8")

        res_outside = parse_js_file_path(outside_file, self.repo_path)
        self.assertEqual(len(res_outside.errors), 1)
        self.assertIn("resolves outside repository root", res_outside.errors[0].error_message)

        # Symlink inside repository
        symlink_file = self.repo_path / "link.js"
        try:
            os.symlink(outside_file, symlink_file)
            symlink_created = True
        except (OSError, NotImplementedError):
            symlink_created = False

        if symlink_created:
            res_sym = parse_js_file_path(symlink_file, self.repo_path)
            self.assertEqual(len(res_sym.errors), 1)
            self.assertIn("Symbolic link", res_sym.errors[0].error_message)

    # 15. The parser never executes analyzed repository source code
    def test_15_parser_never_executes_analyzed_code(self) -> None:
        canary = self.repo_path / "canary.txt"
        canary.write_text("alive", encoding="utf-8")

        danger_code = (
            "const fs = require('fs');\n"
            f"fs.unlinkSync({json.dumps(str(canary))});\n"
            "process.exit(1);\n"
        )
        danger_file = self.repo_path / "danger.js"
        danger_file.write_text(danger_code, encoding="utf-8")

        parse_js_file_path(danger_file, self.repo_path)

        self.assertTrue(canary.exists())
        self.assertEqual(canary.read_text(encoding="utf-8"), "alive")


if __name__ == "__main__":
    unittest.main()
