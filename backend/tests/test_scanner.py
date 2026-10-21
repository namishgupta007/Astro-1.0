"""Automated unit and integration tests for Astral Cartographer's repository scanner."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, mock_open

from app.ingestion.scanner import (
    DEFAULT_MAX_HASH_SIZE_MB,
    SCHEMA_VERSION,
    detect_language,
    is_binary_buffer,
    is_binary_file_by_extension,
    is_sensitive_file,
    main,
    scan_repository,
)


class TestRepositoryScanner(unittest.TestCase):
    """Test suite covering all requirements and scenarios for the repository scanner."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo_path = Path(self.temp_dir.name).resolve()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    # Scenario 1: A valid repository containing Python and Markdown files
    def test_01_valid_repo_python_and_markdown(self) -> None:
        (self.repo_path / "main.py").write_text("print('hello')", encoding="utf-8")
        (self.repo_path / "README.md").write_text("# Test Repo", encoding="utf-8")

        output_file = self.repo_path / "inventory.json"
        inventory = scan_repository(self.repo_path, output_path=output_file)

        self.assertEqual(inventory["schema_version"], SCHEMA_VERSION)
        self.assertEqual(inventory["repository_name"], self.repo_path.name)
        self.assertTrue("scanned_at" in inventory)
        self.assertEqual(inventory["summary"]["total_files"], 2)
        self.assertEqual(inventory["summary"]["hashed_files"], 2)
        self.assertTrue(output_file.exists())

        # Verify output file content matches returned dict
        with open(output_file, "r", encoding="utf-8") as f:
            written_data = json.load(f)
        self.assertEqual(written_data["schema_version"], inventory["schema_version"])
        self.assertEqual(len(written_data["files"]), 2)

    # Scenario 2: Correct relative paths, extensions, sizes, and language detection
    def test_02_relative_paths_extensions_sizes_and_languages(self) -> None:
        src_dir = self.repo_path / "src" / "core"
        src_dir.mkdir(parents=True)
        py_file = src_dir / "app.py"
        py_content = "def run():\n    pass\n"
        py_file.write_bytes(py_content.encode("utf-8"))

        docs_dir = self.repo_path / "docs"
        docs_dir.mkdir()
        md_file = docs_dir / "guide.md"
        md_content = "# Guide\nDetailed guide."
        md_file.write_bytes(md_content.encode("utf-8"))

        inventory = scan_repository(self.repo_path)
        files = {f["path"]: f for f in inventory["files"]}

        self.assertIn("src/core/app.py", files)
        py_record = files["src/core/app.py"]
        self.assertEqual(py_record["extension"], ".py")
        self.assertEqual(py_record["language"], "Python")
        self.assertEqual(py_record["size_bytes"], len(py_content.encode("utf-8")))
        self.assertEqual(py_record["hash_status"], "computed")

        self.assertIn("docs/guide.md", files)
        md_record = files["docs/guide.md"]
        self.assertEqual(md_record["extension"], ".md")
        self.assertEqual(md_record["language"], "Markdown")
        self.assertEqual(md_record["size_bytes"], len(md_content.encode("utf-8")))

    # Scenario 3: SHA-256 values matching the actual file contents
    def test_03_sha256_checksum_accuracy(self) -> None:
        content_a = b"import math\nprint(math.pi)\n"
        content_b = b"const x = 42;\nconsole.log(x);\n"

        file_a = self.repo_path / "math_test.py"
        file_b = self.repo_path / "index.js"
        file_a.write_bytes(content_a)
        file_b.write_bytes(content_b)

        inventory = scan_repository(self.repo_path)
        files = {f["path"]: f for f in inventory["files"]}

        expected_hash_a = hashlib.sha256(content_a).hexdigest()
        expected_hash_b = hashlib.sha256(content_b).hexdigest()

        self.assertEqual(files["math_test.py"]["sha256"], expected_hash_a)
        self.assertEqual(files["index.js"]["sha256"], expected_hash_b)

    # Scenario 4: Correct language counts and total file counts
    def test_04_language_counts_and_total_counts(self) -> None:
        (self.repo_path / "script.py").write_text("x = 1", encoding="utf-8")
        (self.repo_path / "app.ts").write_text("let a: number = 1;", encoding="utf-8")
        (self.repo_path / "style.css").write_text("body { margin: 0; }", encoding="utf-8")
        (self.repo_path / "index.html").write_text("<h1>Hi</h1>", encoding="utf-8")
        (self.repo_path / "main.rs").write_text("fn main() {}", encoding="utf-8")
        (self.repo_path / "main.go").write_text("package main", encoding="utf-8")
        (self.repo_path / "Dockerfile").write_text("FROM alpine", encoding="utf-8")

        inventory = scan_repository(self.repo_path)
        summary = inventory["summary"]

        self.assertEqual(summary["total_files"], 7)
        self.assertEqual(summary["hashed_files"], 7)
        self.assertEqual(summary["binary_files"], 0)
        self.assertEqual(summary["unknown_language_files"], 0)

        expected_languages = {
            "CSS": 1,
            "Dockerfile": 1,
            "Go": 1,
            "HTML": 1,
            "Python": 1,
            "Rust": 1,
            "TypeScript": 1,
        }
        self.assertEqual(summary["language_counts"], expected_languages)

    # Scenario 5: Ignored directories such as .git, node_modules, __pycache__
    def test_05_ignored_directories_skipped(self) -> None:
        (self.repo_path / "kept.py").write_text("print('kept')", encoding="utf-8")

        git_dir = self.repo_path / ".git" / "objects"
        git_dir.mkdir(parents=True)
        (git_dir / "00a1b2").write_text("gitobject", encoding="utf-8")

        nm_dir = self.repo_path / "node_modules" / "lodash"
        nm_dir.mkdir(parents=True)
        (nm_dir / "index.js").write_text("module.exports = {};", encoding="utf-8")

        pycache_dir = self.repo_path / "src" / "__pycache__"
        pycache_dir.mkdir(parents=True)
        (pycache_dir / "app.cpython-310.pyc").write_bytes(b"\x00\x01\x02\x03")

        dist_dir = self.repo_path / "dist"
        dist_dir.mkdir()
        (dist_dir / "bundle.js").write_text("bundled", encoding="utf-8")

        venv_dir = self.repo_path / ".venv" / "lib"
        venv_dir.mkdir(parents=True)
        (venv_dir / "pkg.py").write_text("venv code", encoding="utf-8")

        inventory = scan_repository(self.repo_path)
        paths = [f["path"] for f in inventory["files"]]

        self.assertEqual(paths, ["kept.py"])
        self.assertGreaterEqual(inventory["summary"]["skipped"]["directories"], 5)

    # Scenario 6: Sensitive environment files excluded while safe examples are retained
    def test_06_sensitive_files_excluded_safe_examples_retained(self) -> None:
        # Sensitive files that must be excluded
        (self.repo_path / ".env").write_text("SECRET_KEY=12345", encoding="utf-8")
        (self.repo_path / ".env.local").write_text("LOCAL_SECRET=abc", encoding="utf-8")
        (self.repo_path / ".env.production").write_text("PROD_SECRET=xyz", encoding="utf-8")
        (self.repo_path / "id_rsa").write_text("-----BEGIN RSA PRIVATE KEY-----", encoding="utf-8")
        (self.repo_path / "credentials.json").write_text('{"api_key": "secret"}', encoding="utf-8")
        (self.repo_path / "server.key").write_text("PRIVATE KEY DATA", encoding="utf-8")

        # Safe template files that must be retained
        (self.repo_path / ".env.example").write_text("SECRET_KEY=your_key_here", encoding="utf-8")
        (self.repo_path / ".env.sample").write_text("LOCAL_SECRET=sample", encoding="utf-8")
        (self.repo_path / ".env.template").write_text("TEMPLATE_VAL=foo", encoding="utf-8")
        (self.repo_path / "credentials.example.json").write_text('{"api_key": ""}', encoding="utf-8")
        (self.repo_path / "id_rsa.pub").write_text("ssh-rsa AAAAB3NzaC1yc2E...", encoding="utf-8")

        inventory = scan_repository(self.repo_path)
        paths = [f["path"] for f in inventory["files"]]

        # Sensitive files must NOT be in inventory
        self.assertNotIn(".env", paths)
        self.assertNotIn(".env.local", paths)
        self.assertNotIn(".env.production", paths)
        self.assertNotIn("id_rsa", paths)
        self.assertNotIn("credentials.json", paths)
        self.assertNotIn("server.key", paths)

        # Safe examples MUST be in inventory
        self.assertIn(".env.example", paths)
        self.assertIn(".env.sample", paths)
        self.assertIn(".env.template", paths)
        self.assertIn("credentials.example.json", paths)
        self.assertIn("id_rsa.pub", paths)

        self.assertEqual(inventory["summary"]["skipped"]["sensitive_files"], 6)

        # Verify no secret values leaked in JSON dump
        dumped = json.dumps(inventory)
        self.assertNotIn("12345", dumped)
        self.assertNotIn("PROD_SECRET", dumped)

    # Scenario 7: Binary and oversized files handled according to the hashing rules
    def test_07_binary_and_oversized_files(self) -> None:
        # Binary by extension
        (self.repo_path / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")

        # Binary by content (unknown extension containing null bytes)
        (self.repo_path / "data.custom").write_bytes(b"Header\x00\x01\x02\x03Body")

        # Oversized text file
        large_py = self.repo_path / "large_module.py"
        large_content = "x = 1\n" * 500  # ~3000 bytes
        large_py.write_text(large_content, encoding="utf-8")

        # Normal small file
        (self.repo_path / "small.py").write_text("print('small')", encoding="utf-8")

        # Scan with max_hash_size_mb = 0.001 (approx 1048 bytes)
        inventory = scan_repository(self.repo_path, max_hash_size_mb=0.001)
        files = {f["path"]: f for f in inventory["files"]}

        # PNG file check
        png_rec = files["image.png"]
        self.assertEqual(png_rec["language"], "Binary")
        self.assertEqual(png_rec["hash_status"], "skipped_binary")
        self.assertIsNone(png_rec["sha256"])

        # Content-detected binary file check
        custom_rec = files["data.custom"]
        self.assertEqual(custom_rec["language"], "Binary")
        self.assertEqual(custom_rec["hash_status"], "skipped_binary")
        self.assertIsNone(custom_rec["sha256"])

        # Oversized python file check
        large_rec = files["large_module.py"]
        self.assertEqual(large_rec["language"], "Python")
        self.assertEqual(large_rec["hash_status"], "skipped_too_large")
        self.assertIsNone(large_rec["sha256"])

        # Small python file check
        small_rec = files["small.py"]
        self.assertEqual(small_rec["language"], "Python")
        self.assertEqual(small_rec["hash_status"], "computed")
        self.assertIsNotNone(small_rec["sha256"])

        self.assertEqual(inventory["summary"]["binary_files"], 2)
        self.assertEqual(inventory["summary"]["hashed_files"], 1)

    # Scenario 8: Unknown extensions retained and classified consistently
    def test_08_unknown_extensions_retained_as_unknown(self) -> None:
        (self.repo_path / "manifest.xyz123").write_text("foo=bar\nbaz=qux\n", encoding="utf-8")
        (self.repo_path / "notes.customtext").write_text("Hello text note\n", encoding="utf-8")

        inventory = scan_repository(self.repo_path)
        files = {f["path"]: f for f in inventory["files"]}

        self.assertIn("manifest.xyz123", files)
        rec1 = files["manifest.xyz123"]
        self.assertEqual(rec1["language"], "Unknown")
        self.assertEqual(rec1["extension"], ".xyz123")
        self.assertEqual(rec1["hash_status"], "computed")

        self.assertIn("notes.customtext", files)
        rec2 = files["notes.customtext"]
        self.assertEqual(rec2["language"], "Unknown")
        self.assertEqual(rec2["extension"], ".customtext")
        self.assertEqual(rec2["hash_status"], "computed")

        self.assertEqual(inventory["summary"]["unknown_language_files"], 2)

    # Scenario 9: Missing paths and non-directory paths rejected cleanly
    def test_09_invalid_input_paths_rejected(self) -> None:
        non_existent = self.repo_path / "does_not_exist_dir"
        with self.assertRaises(FileNotFoundError):
            scan_repository(non_existent)

        regular_file = self.repo_path / "some_file.txt"
        regular_file.write_text("hello", encoding="utf-8")
        with self.assertRaises(NotADirectoryError):
            scan_repository(regular_file)

        with self.assertRaises(ValueError):
            scan_repository(self.repo_path, max_hash_size_mb=0)

        with self.assertRaises(ValueError):
            scan_repository(self.repo_path, max_hash_size_mb=-2.0)

    # Scenario 10: Empty repositories handled correctly
    def test_10_empty_repository(self) -> None:
        inventory = scan_repository(self.repo_path)

        self.assertEqual(inventory["summary"]["total_files"], 0)
        self.assertEqual(inventory["summary"]["hashed_files"], 0)
        self.assertEqual(inventory["summary"]["binary_files"], 0)
        self.assertEqual(inventory["summary"]["unknown_language_files"], 0)
        self.assertEqual(inventory["summary"]["language_counts"], {})
        self.assertEqual(inventory["files"], [])

    # Scenario 11: Repeated scans produce deterministic file ordering
    def test_11_deterministic_file_ordering(self) -> None:
        filenames = [
            "zebra.py",
            "apple.py",
            "src/utils.py",
            "src/alpha.py",
            "docs/b_intro.md",
            "docs/a_getting_started.md",
        ]
        for name in filenames:
            p = self.repo_path / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("code", encoding="utf-8")

        scan1 = scan_repository(self.repo_path)
        scan2 = scan_repository(self.repo_path)

        paths1 = [f["path"] for f in scan1["files"]]
        paths2 = [f["path"] for f in scan2["files"]]

        self.assertEqual(paths1, sorted(paths1))
        self.assertEqual(paths1, paths2)

    # Scenario 12: Output inventory is not included in its own file list
    def test_12_output_inventory_not_included(self) -> None:
        (self.repo_path / "code.py").write_text("x = 1", encoding="utf-8")

        output_path = self.repo_path / "output" / "repository_inventory.json"

        # First scan writes the file
        inventory1 = scan_repository(self.repo_path, output_path=output_path)
        self.assertEqual([f["path"] for f in inventory1["files"]], ["code.py"])

        # Second scan while the output file already exists on disk
        inventory2 = scan_repository(self.repo_path, output_path=output_path)
        self.assertEqual([f["path"] for f in inventory2["files"]], ["code.py"])

    # Scenario 13: Symlinks do not cause traversal outside repository
    def test_13_symlinks_skipped_cleanly(self) -> None:
        (self.repo_path / "normal.py").write_text("print(1)", encoding="utf-8")

        # Create external directory with a target file
        with tempfile.TemporaryDirectory() as outside_dir:
            outside_path = Path(outside_dir)
            (outside_path / "secret_outside.py").write_text("secret_code", encoding="utf-8")

            try:
                symlink_dir = self.repo_path / "link_to_outside"
                os.symlink(outside_path, symlink_dir, target_is_directory=True)

                symlink_file = self.repo_path / "link_file.py"
                os.symlink(outside_path / "secret_outside.py", symlink_file)
                symlink_created = True
            except (OSError, NotImplementedError):
                # On Windows without developer mode/admin rights, os.symlink can raise OSError
                symlink_created = False

            if symlink_created:
                inventory = scan_repository(self.repo_path)
                paths = [f["path"] for f in inventory["files"]]

                self.assertEqual(paths, ["normal.py"])
                self.assertNotIn("secret_outside.py", paths)
                self.assertEqual(inventory["summary"]["skipped"]["symlinks"], 2)

        # Mock-based validation to ensure symlink skip logic is verified unconditionally
        with patch("os.path.islink", side_effect=lambda p: Path(p).name.startswith("fake_link")):
            (self.repo_path / "fake_link.py").write_text("print(2)", encoding="utf-8")
            inventory = scan_repository(self.repo_path)
            paths = [f["path"] for f in inventory["files"]]
            self.assertNotIn("fake_link.py", paths)
            self.assertGreaterEqual(inventory["summary"]["skipped"]["symlinks"], 1)

    # Scenario 14: Unreadable files handled gracefully without crashing
    def test_14_unreadable_file_handled_gracefully(self) -> None:
        (self.repo_path / "readable.py").write_text("x = 1", encoding="utf-8")
        unreadable_file = self.repo_path / "unreadable.py"
        unreadable_file.write_text("secret", encoding="utf-8")

        # Simulate read error on unreadable.py while allowing normal reads on other files
        original_open = open

        def guarded_open(file, *args, **kwargs):
            if Path(file).name == "unreadable.py" and "rb" in args or kwargs.get("mode") == "rb":
                raise PermissionError("Permission denied for testing")
            return original_open(file, *args, **kwargs)

        with patch("builtins.open", side_effect=guarded_open):
            inventory = scan_repository(self.repo_path)

        files = {f["path"]: f for f in inventory["files"]}
        self.assertIn("readable.py", files)
        self.assertIn("unreadable.py", files)

        unreadable_rec = files["unreadable.py"]
        self.assertEqual(unreadable_rec["hash_status"], "unreadable")
        self.assertIsNone(unreadable_rec["sha256"])
        self.assertEqual(unreadable_rec["language"], "Python")
        self.assertGreaterEqual(inventory["summary"]["skipped"]["unreadable_files"], 1)

    # Scenario 15: CLI execution and exit codes
    def test_15_cli_execution(self) -> None:
        (self.repo_path / "main.py").write_text("print('cli')", encoding="utf-8")
        out_file = self.repo_path / "cli_output.json"

        # Successful scan
        exit_code = main([str(self.repo_path), "-o", str(out_file)])
        self.assertEqual(exit_code, 0)
        self.assertTrue(out_file.exists())

        # Error on missing path
        exit_code_err = main([str(self.repo_path / "non_existent")])
        self.assertEqual(exit_code_err, 1)


if __name__ == "__main__":
    unittest.main()
