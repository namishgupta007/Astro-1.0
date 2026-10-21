"""Astral Cartographer parsers package."""

from typing import Any


def __getattr__(name: str) -> Any:
    if name in {
        "Call",
        "Export",
        "FileParseResult",
        "Import",
        "JSParseSummary",
        "ParseError",
        "ParseSummary",
        "Symbol",
    }:
        import app.parsers.models as models

        return getattr(models, name)
    if name in {
        "parse_file_path",
        "parse_repository",
        "parse_repository_inventory",
        "parse_source_file",
        "PythonASTVisitor",
    }:
        import app.parsers.python_parser as pp

        return getattr(pp, name)
    if name in {
        "JavaScriptTreeSitterVisitor",
        "parse_js_file_path",
        "parse_js_repository",
        "parse_js_repository_inventory",
        "parse_js_source_code",
    }:
        import app.parsers.javascript_parser as jp

        return getattr(jp, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "Call",
    "Export",
    "FileParseResult",
    "Import",
    "JSParseSummary",
    "JavaScriptTreeSitterVisitor",
    "ParseError",
    "ParseSummary",
    "Symbol",
    "parse_file_path",
    "parse_js_file_path",
    "parse_js_repository",
    "parse_js_repository_inventory",
    "parse_js_source_code",
    "parse_repository",
    "parse_repository_inventory",
    "parse_source_file",
    "PythonASTVisitor",
]
