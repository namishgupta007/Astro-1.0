"""Astral Cartographer - Python AST Structural Parser.

Extracts symbols (functions, methods, classes), imports, function calls,
and syntax errors from Python source files without executing user code.
Integrates with the Step 1 repository scanner inventory.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
from pathlib import Path
import sys
from typing import Any, Optional

from app.parsers.models import (
    Call,
    FileParseResult,
    Import,
    ParseError,
    ParseSummary,
    Symbol,
)

SCHEMA_VERSION: int = 1
DEFAULT_OUTPUT_FILENAME: str = "output/python_analysis.json"


class PythonASTVisitor(ast.NodeVisitor):
    """AST visitor extracting structural symbols, imports, and calls from Python code."""

    def __init__(self, file_path: str, source_code: str) -> None:
        self.file_path: str = file_path
        self.source_code: str = source_code
        self.symbols: list[Symbol] = []
        self.imports: list[Import] = []
        self.calls: list[Call] = []

        # Scope stack: list of (qualified_name, scope_type) where scope_type is "class" or "function"
        self._scope_stack: list[tuple[str, str]] = []

        # Function stack: list of Symbol instances representing the currently active function/method
        self._func_stack: list[Symbol] = []

    def _current_scope_name(self) -> Optional[str]:
        """Return the current hierarchical scope name or None if at module level."""
        if not self._scope_stack:
            return None
        return self._scope_stack[-1][0]

    def _is_direct_class_member(self) -> bool:
        """Return True if the current definition is directly inside a class body."""
        return bool(self._scope_stack and self._scope_stack[-1][1] == "class")

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        parent_scope = self._current_scope_name()
        if parent_scope:
            qualified_name = f"{parent_scope}.{node.name}"
        else:
            qualified_name = node.name

        symbol_id = f"{self.file_path}::{qualified_name}:class:{node.lineno}"

        # Extract base classes
        bases: list[str] = []
        for b in node.bases:
            try:
                bases.append(ast.unparse(b))
            except Exception:
                bases.append("<expr>")

        # Extract decorators
        decorators: list[str] = []
        for d in node.decorator_list:
            try:
                decorators.append(f"@{ast.unparse(d)}")
            except Exception:
                decorators.append("@<expr>")

        # Build readable class signature
        base_str = f"({', '.join(bases)})" if bases else ""
        signature = f"class {node.name}{base_str}"

        end_lineno = getattr(node, "end_lineno", None) or node.lineno

        class_symbol = Symbol(
            id=symbol_id,
            name=node.name,
            qualified_name=qualified_name,
            kind="class",
            file_path=self.file_path,
            lineno=node.lineno,
            end_lineno=end_lineno,
            col_offset=node.col_offset,
            parent_scope=parent_scope,
            parameters=None,
            signature=signature,
            decorators=decorators,
            bases=bases,
            is_async=False,
        )
        self.symbols.append(class_symbol)

        # Enter class scope and traverse body
        self._scope_stack.append((qualified_name, "class"))
        self.generic_visit(node)
        self._scope_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._handle_function(node, is_async=False)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._handle_function(node, is_async=True)

    def _extract_local_variable_names(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> list[str]:
        """Extract names of variables assigned locally within this function body, excluding globals."""
        local_names: set[str] = set()
        global_names: set[str] = set()

        def add_target(target: ast.AST) -> None:
            if isinstance(target, ast.Name):
                local_names.add(target.id)
            elif isinstance(target, (ast.Tuple, ast.List)):
                for elt in target.elts:
                    add_target(elt)

        queue = list(node.body)
        while queue:
            curr = queue.pop(0)
            if isinstance(curr, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            if isinstance(curr, (ast.Global, ast.Nonlocal)):
                global_names.update(curr.names)
            elif isinstance(curr, ast.Assign):
                for t in curr.targets:
                    add_target(t)
            elif isinstance(curr, ast.AnnAssign):
                add_target(curr.target)
            elif isinstance(curr, ast.AugAssign):
                add_target(curr.target)
            elif isinstance(curr, (ast.For, ast.AsyncFor)):
                add_target(curr.target)
            elif isinstance(curr, (ast.With, ast.AsyncWith)):
                for item in curr.items:
                    if item.optional_vars:
                        add_target(item.optional_vars)
            elif isinstance(curr, ast.ExceptHandler):
                if curr.name:
                    local_names.add(curr.name)
            elif isinstance(curr, ast.NamedExpr):
                add_target(curr.target)

            for child in ast.iter_child_nodes(curr):
                if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    queue.append(child)

        local_names.difference_update(global_names)
        return sorted(local_names)

    def _handle_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        is_async: bool,
    ) -> None:
        parent_scope = self._current_scope_name()
        if parent_scope:
            qualified_name = f"{parent_scope}.{node.name}"
        else:
            qualified_name = node.name

        # Classification: method if directly inside class; async_function if async; else function
        if self._is_direct_class_member():
            kind = "method"
        elif is_async:
            kind = "async_function"
        else:
            kind = "function"

        symbol_id = f"{self.file_path}::{qualified_name}:{kind}:{node.lineno}"

        # Extract parameter names
        parameters: list[str] = []
        for a in node.args.posonlyargs:
            parameters.append(a.arg)
        for a in node.args.args:
            parameters.append(a.arg)
        if node.args.vararg:
            parameters.append(f"*{node.args.vararg.arg}")
        for a in node.args.kwonlyargs:
            parameters.append(a.arg)
        if node.args.kwarg:
            parameters.append(f"**{node.args.kwarg.arg}")

        # Extract decorators
        decorators: list[str] = []
        for d in node.decorator_list:
            try:
                decorators.append(f"@{ast.unparse(d)}")
            except Exception:
                decorators.append("@<expr>")

        # Build readable signature using a dummy node without body
        try:
            node_type = type(node)
            dummy = node_type(
                name=node.name,
                args=node.args,
                body=[ast.Pass()],
                decorator_list=[],
                returns=node.returns,
                type_comment=getattr(node, "type_comment", None),
            )
            ast.fix_missing_locations(dummy)
            unparsed = ast.unparse(dummy)
            signature = unparsed.split(":\n")[0]
        except Exception:
            prefix = "async def" if is_async else "def"
            param_str = ", ".join(parameters)
            signature = f"{prefix} {node.name}({param_str})"

        end_lineno = getattr(node, "end_lineno", None) or node.lineno
        local_variables = self._extract_local_variable_names(node)

        func_symbol = Symbol(
            id=symbol_id,
            name=node.name,
            qualified_name=qualified_name,
            kind=kind,
            file_path=self.file_path,
            lineno=node.lineno,
            end_lineno=end_lineno,
            col_offset=node.col_offset,
            parent_scope=parent_scope,
            parameters=parameters,
            signature=signature,
            decorators=decorators,
            bases=None,
            is_async=is_async,
            local_variables=local_variables,
        )
        self.symbols.append(func_symbol)

        # Enter function scope and active function caller stack
        self._scope_stack.append((qualified_name, "function"))
        self._func_stack.append(func_symbol)

        self.generic_visit(node)

        self._func_stack.pop()
        self._scope_stack.pop()

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.imports.append(
                Import(
                    module=alias.name,
                    name=alias.name,
                    alias=alias.asname,
                    file_path=self.file_path,
                    lineno=node.lineno,
                    col_offset=node.col_offset,
                    level=0,
                )
            )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            self.imports.append(
                Import(
                    module=node.module,
                    name=alias.name,
                    alias=alias.asname,
                    file_path=self.file_path,
                    lineno=node.lineno,
                    col_offset=node.col_offset,
                    level=node.level or 0,
                )
            )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        # Full expression as written in source
        try:
            callee_expr = ast.unparse(node.func)
        except Exception:
            callee_expr = "<call_expr>"

        callee_name = self._extract_simple_callee_name(node.func)

        # Identify enclosing caller function/method
        if self._func_stack:
            enclosing = self._func_stack[-1]
            caller = enclosing.qualified_name
            caller_symbol_id = enclosing.id
            is_module_level = False
        else:
            caller = None
            caller_symbol_id = None
            is_module_level = True

        self.calls.append(
            Call(
                callee=callee_expr,
                callee_name=callee_name,
                file_path=self.file_path,
                lineno=node.lineno,
                col_offset=node.col_offset,
                caller=caller,
                caller_symbol_id=caller_symbol_id,
                is_module_level=is_module_level,
            )
        )

        self.generic_visit(node)

    def _extract_simple_callee_name(self, func_node: ast.AST) -> Optional[str]:
        """Extract the simple final identifier for a call target where feasible."""
        if isinstance(func_node, ast.Name):
            return func_node.id
        elif isinstance(func_node, ast.Attribute):
            return func_node.attr
        elif isinstance(func_node, ast.Call):
            # E.g. get_service().process() -> "process"
            return self._extract_simple_callee_name(func_node.func)
        return None


def parse_source_file(source_code: str, file_path: str) -> FileParseResult:
    """Parse a single Python source string into symbols, imports, calls, and errors.

    Args:
        source_code: The Python source code text.
        file_path: The repository-relative normalized file path.

    Returns:
        A FileParseResult containing extracted structures or syntax errors.
    """
    normalized_path = Path(file_path).as_posix()

    try:
        tree = ast.parse(source_code, filename=normalized_path)
    except SyntaxError as err:
        return FileParseResult(
            file_path=normalized_path,
            errors=[
                ParseError(
                    file_path=normalized_path,
                    lineno=err.lineno,
                    col_offset=err.offset,
                    error_message=f"SyntaxError: {err.msg}",
                )
            ],
        )
    except Exception as err:
        return FileParseResult(
            file_path=normalized_path,
            errors=[
                ParseError(
                    file_path=normalized_path,
                    lineno=None,
                    col_offset=None,
                    error_message=f"ParseError: {err}",
                )
            ],
        )

    visitor = PythonASTVisitor(file_path=normalized_path, source_code=source_code)
    visitor.visit(tree)

    return FileParseResult(
        file_path=normalized_path,
        symbols=visitor.symbols,
        imports=visitor.imports,
        calls=visitor.calls,
        errors=[],
    )


def parse_file_path(
    file_path: Path | str,
    repo_root: Path | str,
) -> FileParseResult:
    """Safely read and parse a Python file from disk.

    Ensures the path does not escape the repository root or follow external symlinks.

    Args:
        file_path: Relative or absolute path to the Python file.
        repo_root: Absolute or relative path to the repository root.

    Returns:
        A FileParseResult containing extracted structures or errors.
    """
    repo_root_path = Path(repo_root).resolve()
    target_path = Path(file_path)

    if not target_path.is_absolute():
        full_path = repo_root_path / target_path
    else:
        full_path = target_path

    # Verify that relative path does not escape repository root
    try:
        rel_path = full_path.resolve().relative_to(repo_root_path).as_posix()
    except ValueError:
        return FileParseResult(
            file_path=target_path.as_posix(),
            errors=[
                ParseError(
                    file_path=target_path.as_posix(),
                    lineno=None,
                    col_offset=None,
                    error_message="Path escapes repository root",
                )
            ],
        )

    # Symlink safety check: ensure target does not resolve outside repository root
    if os.path.islink(full_path):
        resolved_link = full_path.resolve()
        try:
            resolved_link.relative_to(repo_root_path)
        except ValueError:
            return FileParseResult(
                file_path=rel_path,
                errors=[
                    ParseError(
                        file_path=rel_path,
                        lineno=None,
                        col_offset=None,
                        error_message="Symbolic link points outside repository root",
                    )
                ],
            )

    if not full_path.exists():
        return FileParseResult(
            file_path=rel_path,
            errors=[
                ParseError(
                    file_path=rel_path,
                    lineno=None,
                    col_offset=None,
                    error_message=f"File not found: {rel_path}",
                )
            ],
        )

    if not full_path.is_file():
        return FileParseResult(
            file_path=rel_path,
            errors=[
                ParseError(
                    file_path=rel_path,
                    lineno=None,
                    col_offset=None,
                    error_message=f"Target is not a regular file: {rel_path}",
                )
            ],
        )

    # Read file content safely
    try:
        source_code = full_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            source_code = full_path.read_text(encoding="utf-8", errors="replace")
        except Exception as err:
            return FileParseResult(
                file_path=rel_path,
                errors=[
                    ParseError(
                        file_path=rel_path,
                        lineno=None,
                        col_offset=None,
                        error_message=f"UnicodeDecodeError: {err}",
                    )
                ],
            )
    except (PermissionError, OSError) as err:
        return FileParseResult(
            file_path=rel_path,
            errors=[
                ParseError(
                    file_path=rel_path,
                    lineno=None,
                    col_offset=None,
                    error_message=f"IOError: {err}",
                )
            ],
        )

    return parse_source_file(source_code=source_code, file_path=rel_path)


def parse_repository_inventory(
    inventory_path: Path | str,
    repo_root: Path | str,
    output_path: Optional[Path | str] = None,
) -> dict[str, Any]:
    """Parse all Python files listed in a repository_inventory.json file.

    Args:
        inventory_path: Path to the JSON inventory generated by Step 1 scanner.
        repo_root: Path to the root of the repository being analyzed.
        output_path: Optional destination path to write python_analysis.json.

    Returns:
        Structured dictionary matching Schema Version 1.

    Raises:
        FileNotFoundError: If repository root or inventory file does not exist.
        NotADirectoryError: If repo_root is not a directory.
    """
    resolved_root = Path(repo_root).resolve()
    if not resolved_root.exists():
        raise FileNotFoundError(f"Repository root does not exist: {resolved_root}")
    if not resolved_root.is_dir():
        raise NotADirectoryError(f"Repository root is not a directory: {resolved_root}")

    inv_path = Path(inventory_path).resolve()
    if not inv_path.exists():
        raise FileNotFoundError(f"Inventory file does not exist: {inv_path}")
    if not inv_path.is_file():
        raise ValueError(f"Inventory path is not a file: {inv_path}")

    with open(inv_path, "r", encoding="utf-8") as f:
        inventory_data = json.load(f)

    repo_name = inventory_data.get("repository_name", resolved_root.name)

    # Filter Python files from the inventory
    all_files = inventory_data.get("files", [])
    python_files = [f for f in all_files if f.get("language") == "Python"]

    all_symbols: list[Symbol] = []
    all_imports: list[Import] = []
    all_calls: list[Call] = []
    all_errors: list[ParseError] = []

    files_parsed: int = 0
    files_with_errors: int = 0

    for file_info in python_files:
        rel_path = file_info["path"]
        result = parse_file_path(file_path=rel_path, repo_root=resolved_root)

        if result.errors:
            files_with_errors += 1
            all_errors.extend(result.errors)
        else:
            files_parsed += 1

        all_symbols.extend(result.symbols)
        all_imports.extend(result.imports)
        all_calls.extend(result.calls)

    # Deterministic sorting
    all_symbols.sort(key=lambda s: (s.file_path, s.lineno, s.col_offset, s.id))
    all_imports.sort(
        key=lambda i: (i.file_path, i.lineno, i.col_offset, i.module or "", i.name)
    )
    all_calls.sort(key=lambda c: (c.file_path, c.lineno, c.col_offset, c.callee))
    all_errors.sort(key=lambda e: (e.file_path, e.lineno or 0, e.col_offset or 0))

    summary = ParseSummary(
        python_files_discovered=len(python_files),
        python_files_parsed=files_parsed,
        python_files_with_errors=files_with_errors,
        symbols_found=len(all_symbols),
        imports_found=len(all_imports),
        calls_found=len(all_calls),
    )

    analysis_result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "repository_name": repo_name,
        "summary": summary.to_dict(),
        "symbols": [s.to_dict() for s in all_symbols],
        "imports": [i.to_dict() for i in all_imports],
        "calls": [c.to_dict() for c in all_calls],
        "parse_errors": [e.to_dict() for e in all_errors],
    }

    if output_path is not None:
        out_p = Path(output_path).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)
        with open(out_p, "w", encoding="utf-8") as f:
            json.dump(analysis_result, f, indent=2, ensure_ascii=False)
            f.write("\n")

    return analysis_result


def parse_repository(
    repo_root: Path | str,
    output_path: Optional[Path | str] = None,
) -> dict[str, Any]:
    """Directly discover and parse all Python files in a repository root.

    Used when an inventory file is not available.
    """
    from app.ingestion.scanner import scan_repository

    temp_inv = scan_repository(repository_path=repo_root, output_path=None)

    # Write temporary inventory or process directly in memory
    repo_name = temp_inv.get("repository_name", Path(repo_root).name)
    resolved_root = Path(repo_root).resolve()

    python_files = [f for f in temp_inv.get("files", []) if f.get("language") == "Python"]

    all_symbols: list[Symbol] = []
    all_imports: list[Import] = []
    all_calls: list[Call] = []
    all_errors: list[ParseError] = []

    files_parsed = 0
    files_with_errors = 0

    for file_info in python_files:
        rel_path = file_info["path"]
        result = parse_file_path(file_path=rel_path, repo_root=resolved_root)

        if result.errors:
            files_with_errors += 1
            all_errors.extend(result.errors)
        else:
            files_parsed += 1

        all_symbols.extend(result.symbols)
        all_imports.extend(result.imports)
        all_calls.extend(result.calls)

    all_symbols.sort(key=lambda s: (s.file_path, s.lineno, s.col_offset, s.id))
    all_imports.sort(
        key=lambda i: (i.file_path, i.lineno, i.col_offset, i.module or "", i.name)
    )
    all_calls.sort(key=lambda c: (c.file_path, c.lineno, c.col_offset, c.callee))
    all_errors.sort(key=lambda e: (e.file_path, e.lineno or 0, e.col_offset or 0))

    summary = ParseSummary(
        python_files_discovered=len(python_files),
        python_files_parsed=files_parsed,
        python_files_with_errors=files_with_errors,
        symbols_found=len(all_symbols),
        imports_found=len(all_imports),
        calls_found=len(all_calls),
    )

    analysis_result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "repository_name": repo_name,
        "summary": summary.to_dict(),
        "symbols": [s.to_dict() for s in all_symbols],
        "imports": [i.to_dict() for i in all_imports],
        "calls": [c.to_dict() for c in all_calls],
        "parse_errors": [e.to_dict() for e in all_errors],
    }

    if output_path is not None:
        out_p = Path(output_path).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)
        with open(out_p, "w", encoding="utf-8") as f:
            json.dump(analysis_result, f, indent=2, ensure_ascii=False)
            f.write("\n")

    return analysis_result


def parse_args(args: Optional[list[str]] = None) -> argparse.Namespace:
    """Parse CLI arguments for the Python AST parser."""
    parser = argparse.ArgumentParser(
        prog="python -m app.parsers.python_parser",
        description="Astral Cartographer - Python AST Structural Parser",
    )
    parser.add_argument(
        "-r",
        "--root",
        type=str,
        default=".",
        help="Path to the repository root directory (default: .)",
    )
    parser.add_argument(
        "-i",
        "--inventory",
        type=str,
        default=None,
        help="Path to repository_inventory.json from Step 1 scanner",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default=DEFAULT_OUTPUT_FILENAME,
        help=f"Destination path for python_analysis.json (default: {DEFAULT_OUTPUT_FILENAME})",
    )
    return parser.parse_args(args)


def print_cli_summary(analysis: dict[str, Any], output_path: Optional[Path]) -> None:
    """Display a formatted summary of the parser results in the terminal."""
    summary = analysis["summary"]
    errors = analysis.get("parse_errors", [])

    sep = "=" * 60
    print(sep)
    print(" Astral Cartographer - Python AST Parser Summary")
    print(sep)
    print(f"Repository Name:         {analysis['repository_name']}")
    if output_path:
        print(f"Output File:             {output_path}")
    print(f"Schema Version:          {analysis['schema_version']}")
    print("-" * 60)
    print("Files Processed:")
    print(f"  Discovered (Python):   {summary['python_files_discovered']}")
    print(f"  Parsed Successfully:   {summary['python_files_parsed']}")
    print(f"  Failed with Errors:    {summary['python_files_with_errors']}")
    print("-" * 60)
    print("Extractions:")
    print(f"  Symbols Extracted:     {summary['symbols_found']}")
    print(f"  Imports Extracted:     {summary['imports_found']}")
    print(f"  Calls Extracted:       {summary['calls_found']}")
    print(f"  Parse Errors:          {len(errors)}")

    if errors:
        print("-" * 60)
        print("Encountered Errors (First 5):")
        for err in errors[:5]:
            loc = f":{err['lineno']}" if err.get("lineno") else ""
            print(f"  {err['file_path']}{loc} - {err['error_message']}")

    print(sep)
    print("AST analysis completed successfully.")


def main(argv: Optional[list[str]] = None) -> int:
    """CLI execution entrypoint."""
    args = parse_args(argv)

    try:
        repo_root = Path(args.root).resolve()
        output_path = Path(args.output).resolve() if args.output else None

        if args.inventory:
            inv_path = Path(args.inventory).resolve()
            analysis = parse_repository_inventory(
                inventory_path=inv_path,
                repo_root=repo_root,
                output_path=output_path,
            )
        else:
            # Check if default inventory exists in root or cwd
            default_inv = Path("output/repository_inventory.json").resolve()
            if default_inv.exists():
                analysis = parse_repository_inventory(
                    inventory_path=default_inv,
                    repo_root=repo_root,
                    output_path=output_path,
                )
            else:
                analysis = parse_repository(
                    repo_root=repo_root,
                    output_path=output_path,
                )

        print_cli_summary(analysis, output_path)
        return 0

    except (FileNotFoundError, NotADirectoryError, ValueError) as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1
    except PermissionError as err:
        print(f"Filesystem permission error: {err}", file=sys.stderr)
        return 1
    except Exception as err:
        print(f"Unexpected error during AST analysis: {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
