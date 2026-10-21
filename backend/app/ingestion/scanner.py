"""Astral Cartographer - Local Repository Scanner.

Inventories a local repository, categorizes source files, detects languages,
computes deterministic SHA-256 content hashes, filters sensitive/ignored assets,
and generates a structured JSON inventory report.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Set, Tuple, Union

# Schema version of the generated inventory
SCHEMA_VERSION: int = 1

# Default configuration values
DEFAULT_MAX_HASH_SIZE_MB: float = 2.0
DEFAULT_CHUNK_SIZE: int = 65536  # 64 KB read buffer
DEFAULT_OUTPUT_FILENAME: str = "output/repository_inventory.json"

# Directories that must be ignored during repository traversal
IGNORED_DIRECTORY_NAMES: frozenset[str] = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".venv",
        "venv",
        "env",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".next",
        ".nuxt",
        ".turbo",
        "dist",
        "build",
        "coverage",
        "target",
        "vendor",
        "pods",
        # Common IDE & tool directories
        ".idea",
        ".vscode",
        ".tox",
    }
)

# Common binary file extensions to skip hashing and mark as Binary
KNOWN_BINARY_EXTENSIONS: frozenset[str] = frozenset(
    {
        # Executables, libraries, bytecode
        ".exe",
        ".dll",
        ".so",
        ".dylib",
        ".bin",
        ".obj",
        ".o",
        ".a",
        ".lib",
        ".class",
        ".pyc",
        ".pyo",
        ".pyd",
        ".wasm",
        # Archives and compressed
        ".zip",
        ".tar",
        ".gz",
        ".tgz",
        ".bz2",
        ".xz",
        ".7z",
        ".rar",
        ".iso",
        ".jar",
        ".war",
        ".ear",
        # Images
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".bmp",
        ".ico",
        ".webp",
        ".tiff",
        ".tif",
        # Audio & Video
        ".mp3",
        ".wav",
        ".ogg",
        ".flac",
        ".aac",
        ".m4a",
        ".mp4",
        ".avi",
        ".mov",
        ".mkv",
        ".webm",
        ".flv",
        ".wmv",
        # Documents & Fonts
        ".pdf",
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".ppt",
        ".pptx",
        ".ttf",
        ".otf",
        ".woff",
        ".woff2",
        ".eot",
        # Database & storage
        ".db",
        ".sqlite",
        ".sqlite3",
    }
)

# Extension mapping to human-readable language names
LANGUAGE_EXTENSIONS: dict[str, str] = {
    # Python
    ".py": "Python",
    ".pyw": "Python",
    ".pyi": "Python",
    # JavaScript
    ".js": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".jsx": "JavaScript",
    # TypeScript
    ".ts": "TypeScript",
    ".mts": "TypeScript",
    ".cts": "TypeScript",
    ".tsx": "TypeScript",
    # Java
    ".java": "Java",
    # C
    ".c": "C",
    ".h": "C",
    # C++
    ".cpp": "C++",
    ".hpp": "C++",
    ".cc": "C++",
    ".hh": "C++",
    ".cxx": "C++",
    ".hxx": "C++",
    ".c++": "C++",
    ".h++": "C++",
    # Go
    ".go": "Go",
    # Rust
    ".rs": "Rust",
    # PHP
    ".php": "PHP",
    ".phtml": "PHP",
    ".php3": "PHP",
    ".php4": "PHP",
    ".php5": "PHP",
    ".phps": "PHP",
    # Ruby
    ".rb": "Ruby",
    ".rake": "Ruby",
    ".gemspec": "Ruby",
    # Swift
    ".swift": "Swift",
    # Kotlin
    ".kt": "Kotlin",
    ".kts": "Kotlin",
    # C#
    ".cs": "C#",
    ".csx": "C#",
    # HTML
    ".html": "HTML",
    ".htm": "HTML",
    # CSS & Preprocessors
    ".css": "CSS",
    ".scss": "SCSS",
    ".sass": "Sass",
    ".less": "Less",
    # JSON, YAML, TOML, XML
    ".json": "JSON",
    ".jsonc": "JSON",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".toml": "TOML",
    ".xml": "XML",
    # Markdown
    ".md": "Markdown",
    ".markdown": "Markdown",
    ".mdown": "Markdown",
    ".mkd": "Markdown",
    # SQL
    ".sql": "SQL",
    # Shell scripts
    ".sh": "Shell",
    ".bash": "Shell",
    ".zsh": "Shell",
    ".ksh": "Shell",
    ".fish": "Shell",
    ".bat": "Batchfile",
    ".cmd": "Batchfile",
    ".ps1": "PowerShell",
    ".psm1": "PowerShell",
    # Vue and Svelte
    ".vue": "Vue",
    ".svelte": "Svelte",
    # Additional languages
    ".r": "R",
    ".dart": "Dart",
    ".scala": "Scala",
    ".lua": "Lua",
    ".graphql": "GraphQL",
    ".gql": "GraphQL",
    ".proto": "Protocol Buffers",
    ".tex": "TeX",
    ".rst": "reStructuredText",
    ".ini": "INI",
    ".cfg": "Config",
    ".conf": "Config",
}

# Recognized extensionless or special filenames
EXACT_FILENAMES: dict[str, str] = {
    "dockerfile": "Dockerfile",
    "makefile": "Makefile",
    "jenkinsfile": "Jenkinsfile",
    "vagrantfile": "Vagrantfile",
    "containerfile": "Containerfile",
    "gemfile": "Ruby",
    "rakefile": "Ruby",
    "procfile": "Procfile",
    "cmakelists.txt": "CMake",
}

# Suffixes and markers indicating a file is a safe template/example rather than actual credentials
SAFE_TEMPLATE_SUFFIXES: tuple[str, ...] = (
    ".example",
    ".sample",
    ".template",
    ".dist",
    ".default",
    ".defaults",
)

SAFE_TEMPLATE_MARKERS: tuple[str, ...] = (
    ".example.",
    ".sample.",
    ".template.",
    ".dist.",
    ".default.",
)

# Known credential and secret filenames
SENSITIVE_FILENAMES: frozenset[str] = frozenset(
    {
        "credentials.json",
        "client_secret.json",
        "client_secrets.json",
        "service-account.json",
        "service_account.json",
        "service-account-key.json",
        ".npmrc",
        ".pypirc",
        ".netrc",
        ".htpasswd",
        ".dockercfg",
        "docker-config.json",
        "secrets.json",
        "secret.json",
        "secrets.yaml",
        "secret.yaml",
        "secrets.yml",
        "secret.yml",
        "secrets.toml",
        "secret.toml",
        "master.key",
        "oauth-credentials.json",
    }
)

# Extensions associated with cryptographic private keys or sensitive credentials
SENSITIVE_KEY_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".pem",
        ".key",
        ".pkcs12",
        ".pfx",
        ".p12",
        ".kdbx",
        ".keystore",
        ".jks",
    }
)

# Common SSH private key base prefixes
SSH_KEY_PREFIXES: tuple[str, ...] = (
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "id_xmss",
)


def is_sensitive_file(file_path: Path) -> bool:
    """Determine whether a file is a sensitive secret or credential file.

    Safe templates and examples (e.g. .env.example, credentials.example.json)
    are explicitly retained.
    """
    name = file_path.name
    lower_name = name.lower()

    # 1. Retain safe templates and examples
    if any(lower_name.endswith(suffix) for suffix in SAFE_TEMPLATE_SUFFIXES):
        return False
    if any(marker in lower_name for marker in SAFE_TEMPLATE_MARKERS):
        return False
    if lower_name in {".env.example", ".env.sample", ".env.template", ".env.dist"}:
        return False

    # 2. Skip .env files (e.g. .env, .env.local, .env.production, .env.test)
    if lower_name == ".env" or lower_name.startswith(".env."):
        return True

    # 3. Skip private SSH keys
    for prefix in SSH_KEY_PREFIXES:
        if lower_name == prefix or lower_name.startswith(f"{prefix}."):
            # Public keys ending in .pub are safe to retain
            if not lower_name.endswith(".pub"):
                return True

    # 4. Skip private key patterns and extensions
    if file_path.suffix.lower() in SENSITIVE_KEY_EXTENSIONS:
        return True

    if ("private_key" in lower_name or "privatekey" in lower_name) and not lower_name.endswith(".pub"):
        return True

    # 5. Skip known credential file names
    if lower_name in SENSITIVE_FILENAMES:
        return True

    return False


def is_binary_file_by_extension(file_path: Path) -> bool:
    """Check if the file's extension indicates a known binary format."""
    return file_path.suffix.lower() in KNOWN_BINARY_EXTENSIONS


def is_binary_buffer(buffer: bytes) -> bool:
    """Inspect a byte buffer to check if it contains binary content.

    Uses standard Git-style heuristics: checking for null bytes and
    proportions of non-text control characters, while properly handling
    UTF-16 BOMs.
    """
    if not buffer:
        return False

    # Handle UTF-16 Byte Order Marks
    if buffer.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            buffer.decode("utf-16")
            return False
        except UnicodeDecodeError:
            return True

    # Presence of null byte indicates binary content
    if b"\x00" in buffer:
        return True

    # Check ratio of non-printable ASCII control characters
    # Allowed text characters: whitespace, carriage return, newline, tab, bell, etc.
    text_chars = bytearray({7, 8, 9, 10, 12, 13, 27} | set(range(0x20, 0x100)) - {0x7F})
    non_text = buffer.translate(None, text_chars)
    return len(non_text) / len(buffer) > 0.30


def detect_language(file_path: Path, is_binary: bool = False) -> str:
    """Determine human-readable language or file format name.

    Returns:
        Human-readable language name, 'Binary', or 'Unknown'.
    """
    if is_binary:
        return "Binary"

    lower_name = file_path.name.lower()

    # Exact filename matches (e.g. Dockerfile, Makefile)
    if lower_name in EXACT_FILENAMES:
        return EXACT_FILENAMES[lower_name]

    # Dockerfile variations (e.g. Dockerfile.dev, Dockerfile.prod)
    if lower_name.startswith("dockerfile.") or lower_name == "dockerfile":
        return "Dockerfile"

    # Environment template files
    if lower_name.startswith(".env.") and any(lower_name.endswith(s) for s in SAFE_TEMPLATE_SUFFIXES):
        return "Config"

    # Extension match
    suffix = file_path.suffix.lower()
    if suffix in LANGUAGE_EXTENSIONS:
        return LANGUAGE_EXTENSIONS[suffix]

    return "Unknown"


def process_file(
    file_path: Path,
    repo_root: Path,
    max_hash_size_bytes: int,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> dict[str, Any]:
    """Inspect a single file, detect language/type, and compute SHA-256 where eligible.

    Does not raise exceptions on permission or filesystem read errors; instead returns
    a record with hash_status='unreadable'.
    """
    try:
        rel_path = file_path.relative_to(repo_root)
        posix_path = rel_path.as_posix()
    except ValueError:
        posix_path = file_path.as_posix()

    extension = file_path.suffix.lower()

    # Inspect file size and access
    try:
        stat_result = file_path.stat()
        size_bytes = stat_result.st_size
    except (PermissionError, OSError):
        return {
            "path": posix_path,
            "extension": extension,
            "language": detect_language(file_path, is_binary=False),
            "size_bytes": 0,
            "sha256": None,
            "hash_status": "unreadable",
        }

    # 1. Check known binary extensions
    if is_binary_file_by_extension(file_path):
        return {
            "path": posix_path,
            "extension": extension,
            "language": "Binary",
            "size_bytes": size_bytes,
            "sha256": None,
            "hash_status": "skipped_binary",
        }

    is_oversized = size_bytes > max_hash_size_bytes

    # 2. Inspect content for binary check and hash calculation
    try:
        with open(file_path, "rb") as f:
            # Read first chunk to test for binary content
            first_chunk_size = min(chunk_size, 4096) if is_oversized else chunk_size
            first_chunk = f.read(first_chunk_size)

            if is_binary_buffer(first_chunk):
                return {
                    "path": posix_path,
                    "extension": extension,
                    "language": "Binary",
                    "size_bytes": size_bytes,
                    "sha256": None,
                    "hash_status": "skipped_binary",
                }

            language = detect_language(file_path, is_binary=False)

            # Oversized text file
            if is_oversized:
                return {
                    "path": posix_path,
                    "extension": extension,
                    "language": language,
                    "size_bytes": size_bytes,
                    "sha256": None,
                    "hash_status": "skipped_too_large",
                }

            # Eligible text file within size threshold: compute SHA-256 in chunks
            hasher = hashlib.sha256()
            hasher.update(first_chunk)
            while chunk := f.read(chunk_size):
                hasher.update(chunk)

            return {
                "path": posix_path,
                "extension": extension,
                "language": language,
                "size_bytes": size_bytes,
                "sha256": hasher.hexdigest(),
                "hash_status": "computed",
            }

    except (PermissionError, OSError):
        return {
            "path": posix_path,
            "extension": extension,
            "language": detect_language(file_path, is_binary=False),
            "size_bytes": size_bytes,
            "sha256": None,
            "hash_status": "unreadable",
        }


def scan_repository(
    repository_path: Path | str,
    output_path: Optional[Path | str] = None,
    max_hash_size_mb: float = DEFAULT_MAX_HASH_SIZE_MB,
) -> dict[str, Any]:
    """Scan a local repository and return its structured file inventory.

    Args:
        repository_path: Path to the local repository root directory.
        output_path: Optional path to write the JSON inventory. Parent
            directories will be created if needed.
        max_hash_size_mb: Maximum file size in megabytes to compute SHA-256.
            Files larger than this are assigned hash_status='skipped_too_large'.

    Returns:
        Structured inventory dictionary conforming to schema version 1.

    Raises:
        FileNotFoundError: If repository_path does not exist.
        NotADirectoryError: If repository_path is not a directory.
        ValueError: If max_hash_size_mb is not a positive number.
        IsADirectoryError: If output_path points to an existing directory.
    """
    # Validate max_hash_size_mb
    if not isinstance(max_hash_size_mb, (int, float)) or max_hash_size_mb <= 0:
        raise ValueError(
            f"max_hash_size_mb must be a positive number, received: {max_hash_size_mb!r}"
        )

    # Validate and resolve repository path
    raw_repo_path = Path(repository_path).expanduser()
    if not raw_repo_path.exists():
        raise FileNotFoundError(f"Repository path does not exist: {raw_repo_path}")
    if not raw_repo_path.is_dir():
        raise NotADirectoryError(f"Repository path is not a directory: {raw_repo_path}")

    resolved_repo_path = raw_repo_path.resolve()

    # Validate output path if specified
    resolved_output: Optional[Path] = None
    if output_path is not None:
        out_p = Path(output_path).expanduser().resolve()
        if out_p.exists() and out_p.is_dir():
            raise IsADirectoryError(
                f"Output path must be a file, but points to an existing directory: {out_p}"
            )
        if out_p == resolved_repo_path:
            raise ValueError(
                f"Output path cannot be the repository root directory: {out_p}"
            )
        resolved_output = out_p

    max_hash_bytes = int(max_hash_size_mb * 1024 * 1024)

    skipped_stats: dict[str, int] = {
        "directories": 0,
        "sensitive_files": 0,
        "symlinks": 0,
        "unreadable_files": 0,
    }

    file_records: list[dict[str, Any]] = []

    def on_walk_error(err: OSError) -> None:
        skipped_stats["unreadable_files"] += 1

    # Traverse directory tree without following symlinks
    for root_dir, dirnames, filenames in os.walk(
        resolved_repo_path,
        topdown=True,
        followlinks=False,
        onerror=on_walk_error,
    ):
        root_path = Path(root_dir)

        # Filter directories to visit
        dirs_to_keep: list[str] = []
        for d in sorted(dirnames):
            dir_full_path = root_path / d

            # Symlink directories are skipped
            if os.path.islink(dir_full_path):
                skipped_stats["symlinks"] += 1
                continue

            # Ignored directory names are pruned
            if d.lower() in IGNORED_DIRECTORY_NAMES:
                skipped_stats["directories"] += 1
                continue

            dirs_to_keep.append(d)

        dirnames[:] = dirs_to_keep

        # Inspect files
        for fname in sorted(filenames):
            file_full_path = root_path / fname

            # Skip symlink files
            if os.path.islink(file_full_path):
                skipped_stats["symlinks"] += 1
                continue

            # Exclude the generated inventory file itself
            try:
                if resolved_output and file_full_path.resolve() == resolved_output:
                    continue
            except (PermissionError, OSError):
                pass

            # Skip sensitive files
            if is_sensitive_file(file_full_path):
                skipped_stats["sensitive_files"] += 1
                continue

            # Process file
            record = process_file(
                file_path=file_full_path,
                repo_root=resolved_repo_path,
                max_hash_size_bytes=max_hash_bytes,
            )

            if record["hash_status"] == "unreadable":
                skipped_stats["unreadable_files"] += 1

            file_records.append(record)

    # Sort file records deterministically by relative path
    file_records.sort(key=lambda r: r["path"])

    # Aggregate summary metrics
    total_files = len(file_records)
    hashed_files = sum(1 for r in file_records if r["hash_status"] == "computed")
    binary_files = sum(1 for r in file_records if r["hash_status"] == "skipped_binary")
    unknown_language_files = sum(
        1 for r in file_records if r["language"] == "Unknown"
    )

    language_counts: dict[str, int] = {}
    for r in file_records:
        lang = r["language"]
        if lang not in ("Binary", "Unknown"):
            language_counts[lang] = language_counts.get(lang, 0) + 1

    # Deterministic alphabetical ordering for languages
    language_counts = dict(sorted(language_counts.items()))

    scanned_at_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    summary: dict[str, Any] = {
        "total_files": total_files,
        "hashed_files": hashed_files,
        "binary_files": binary_files,
        "unknown_language_files": unknown_language_files,
        "language_counts": language_counts,
        "skipped": skipped_stats,
        "max_hash_size_mb": float(max_hash_size_mb),
    }

    inventory: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "repository_name": resolved_repo_path.name,
        "scanned_at": scanned_at_iso,
        "summary": summary,
        "files": file_records,
    }

    # Write output JSON file if destination was provided
    if resolved_output is not None:
        resolved_output.parent.mkdir(parents=True, exist_ok=True)
        with open(resolved_output, "w", encoding="utf-8") as f:
            json.dump(inventory, f, indent=2, ensure_ascii=False)
            f.write("\n")

    return inventory


def parse_args(args: Optional[list[str]] = None) -> argparse.Namespace:
    """Parse command line arguments for the repository scanner."""
    parser = argparse.ArgumentParser(
        prog="python -m app.ingestion.scanner",
        description="Astral Cartographer - Local Repository Scanner",
    )
    parser.add_argument(
        "repository_path",
        type=str,
        help="Path to the repository directory to scan",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default=DEFAULT_OUTPUT_FILENAME,
        help=f"Destination path for JSON inventory (default: {DEFAULT_OUTPUT_FILENAME})",
    )
    parser.add_argument(
        "--max-hash-size-mb",
        type=float,
        default=DEFAULT_MAX_HASH_SIZE_MB,
        help=f"Maximum file size in MB to compute SHA-256 hash (default: {DEFAULT_MAX_HASH_SIZE_MB})",
    )
    return parser.parse_args(args)


def print_cli_summary(inventory: dict[str, Any], output_path: Optional[Path]) -> None:
    """Display a formatted summary of the scan results in the terminal."""
    summary = inventory["summary"]
    skipped = summary["skipped"]

    sep = "=" * 60
    print(sep)
    print(" Astral Cartographer - Repository Scan Summary")
    print(sep)
    print(f"Repository Name:     {inventory['repository_name']}")
    if output_path:
        print(f"Output File:         {output_path}")
    print(f"Scanned At (UTC):    {inventory['scanned_at']}")
    print(f"Schema Version:      {inventory['schema_version']}")
    print("-" * 60)
    print("Files Scanned:")
    print(f"  Total Files:       {summary['total_files']}")
    print(f"  Hashed Files:      {summary['hashed_files']}")
    print(f"  Binary Files:      {summary['binary_files']}")
    print(f"  Unknown Language:  {summary['unknown_language_files']}")
    print(f"  Max Hash Size:     {summary['max_hash_size_mb']} MB")

    print("-" * 60)
    print("Languages Detected:")
    if summary["language_counts"]:
        for lang, count in summary["language_counts"].items():
            print(f"  {lang:<18} {count}")
    else:
        print("  (None)")

    print("-" * 60)
    print("Skipped Items:")
    print(f"  Directories:       {skipped['directories']}")
    print(f"  Sensitive Files:   {skipped['sensitive_files']}")
    print(f"  Symlinks:          {skipped['symlinks']}")
    print(f"  Unreadable Files:  {skipped['unreadable_files']}")
    print(sep)
    print("Scan completed successfully.")


def main(argv: Optional[list[str]] = None) -> int:
    """CLI execution entrypoint."""
    args = parse_args(argv)

    try:
        output_path = Path(args.output).resolve()
        inventory = scan_repository(
            repository_path=args.repository_path,
            output_path=output_path,
            max_hash_size_mb=args.max_hash_size_mb,
        )
        print_cli_summary(inventory, output_path)
        return 0

    except (FileNotFoundError, NotADirectoryError, IsADirectoryError, ValueError) as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1
    except PermissionError as err:
        print(f"Filesystem permission error: {err}", file=sys.stderr)
        return 1
    except Exception as err:
        print(f"Unexpected error during scan: {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
