"""Bounded read-only access to explicitly allowed engineering workspace text."""

from __future__ import annotations

import fnmatch
import hashlib
from pathlib import Path
from typing import Any, Iterator


ALLOWED_TEXT_SUFFIXES = frozenset({
    ".bsam", ".csv", ".ele", ".in", ".ini", ".json", ".log", ".lst",
    ".md", ".ssn", ".toml", ".txt", ".yaml", ".yml",
})
BLOCKED_DIRECTORY_NAMES = frozenset({
    ".aws", ".azure", ".bsam-agent", ".config", ".git", ".gnupg", ".hg",
    ".kube", ".mypy_cache", ".pytest_cache", ".ssh", ".svn", ".venv",
    "__pycache__", "node_modules", "venv",
})
BLOCKED_FILE_NAMES = frozenset({
    ".env", ".npmrc", ".pypirc", "credentials.json", "secrets.json",
})
BLOCKED_SUFFIXES = frozenset({".key", ".p12", ".pem", ".pfx"})
MAX_FILE_BYTES = 1_048_576
MAX_LIST_FILES = 500
MAX_SEARCH_FILES = 2_000
MAX_READ_CHARACTERS = 32_768
MAX_SEARCH_MATCHES = 200


class WorkspaceReadError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _relative_text(path: Path, root: Path) -> str:
    return str(path.relative_to(root)).replace("\\", "/")


def _resolve(
    workspace_root: Path,
    value: str,
    role: str,
    *,
    expect_directory: bool | None = None,
) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise WorkspaceReadError("invalid_arguments", f"{role} must be a non-empty relative path")
    supplied = Path(value)
    if supplied.is_absolute():
        raise WorkspaceReadError("path_not_allowed", f"{role} must be relative to the workspace")
    cursor = workspace_root
    for part in supplied.parts:
        if part in {"", "."}:
            continue
        if part == "..":
            raise WorkspaceReadError("path_not_allowed", f"{role} escapes the workspace")
        if part.casefold() in BLOCKED_DIRECTORY_NAMES or part.startswith("."):
            raise WorkspaceReadError("path_not_allowed", f"{role} enters a blocked directory")
        cursor = cursor / part
        if cursor.exists() and cursor.is_symlink():
            raise WorkspaceReadError("path_not_allowed", f"{role} traverses a symbolic link")
    resolved = (workspace_root / supplied).resolve()
    if not resolved.is_relative_to(workspace_root):
        raise WorkspaceReadError("path_not_allowed", f"{role} escapes the workspace")
    if not resolved.exists():
        raise WorkspaceReadError("path_not_found", f"{role} does not exist: {value}")
    if expect_directory is True and not resolved.is_dir():
        raise WorkspaceReadError("invalid_arguments", f"{role} is not a directory: {value}")
    if expect_directory is False and not resolved.is_file():
        raise WorkspaceReadError("invalid_arguments", f"{role} is not a file: {value}")
    return resolved


def _allowed_file(path: Path) -> bool:
    name = path.name.casefold()
    if name.startswith(".") or name in BLOCKED_FILE_NAMES or name.startswith(".env."):
        return False
    if path.suffix.casefold() in BLOCKED_SUFFIXES:
        return False
    return path.suffix.casefold() in ALLOWED_TEXT_SUFFIXES


def _iter_allowed_files(root: Path, directory: Path) -> Iterator[Path]:
    pending = [directory]
    while pending:
        entry = pending.pop()
        if entry.is_symlink():
            continue
        if entry.is_dir():
            if entry != directory and (
                entry.name.startswith(".")
                or entry.name.casefold() in BLOCKED_DIRECTORY_NAMES
            ):
                continue
            children = sorted(entry.iterdir(), key=lambda item: item.name.casefold(), reverse=True)
            pending.extend(children)
            continue
        if entry.is_file() and _allowed_file(entry):
            yield entry


def _positive_limit(value: int, maximum: int, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= maximum:
        raise WorkspaceReadError(
            "invalid_arguments", f"{name} must be an integer from 1 through {maximum}",
        )
    return value


def _read_utf8(path: Path) -> tuple[str, bytes]:
    data = path.read_bytes()
    if len(data) > MAX_FILE_BYTES:
        raise WorkspaceReadError(
            "file_too_large", f"allowed text file exceeds {MAX_FILE_BYTES} bytes",
        )
    if b"\x00" in data:
        raise WorkspaceReadError("unsupported_file", "binary files are not readable")
    try:
        return data.decode("utf-8-sig"), data
    except UnicodeDecodeError as exc:
        raise WorkspaceReadError(
            "unsupported_encoding", "allowed text files must use UTF-8 or ASCII",
        ) from exc


def list_workspace_files(
    workspace_root: Path,
    directory: str = ".",
    pattern: str = "*",
    max_files: int = 100,
) -> dict[str, Any]:
    root = workspace_root.resolve()
    selected = _resolve(root, directory, "directory", expect_directory=True)
    limit = _positive_limit(max_files, MAX_LIST_FILES, "max_files")
    if not isinstance(pattern, str) or not pattern or len(pattern) > 128:
        raise WorkspaceReadError("invalid_arguments", "pattern must contain 1 to 128 characters")
    files: list[dict[str, Any]] = []
    truncated = False
    for path in _iter_allowed_files(root, selected):
        relative = _relative_text(path, root)
        if not fnmatch.fnmatchcase(relative.casefold(), pattern.casefold()):
            continue
        if len(files) == limit:
            truncated = True
            break
        files.append({
            "path": relative,
            "bytes": path.stat().st_size,
            "suffix": path.suffix.casefold(),
        })
    files.sort(key=lambda item: str(item["path"]).casefold())
    return {
        "directory": _relative_text(selected, root) if selected != root else ".",
        "pattern": pattern,
        "files": files,
        "truncated": truncated,
        "summary": {"files": len(files), "truncated": truncated},
    }


def read_allowed_text_file(
    workspace_root: Path,
    path: str,
    start_line: int = 1,
    max_lines: int = 200,
    max_characters: int = 16_000,
) -> dict[str, Any]:
    root = workspace_root.resolve()
    selected = _resolve(root, path, "path", expect_directory=False)
    if not _allowed_file(selected):
        raise WorkspaceReadError("unsupported_file", "file type is not allowed for general reading")
    first = _positive_limit(start_line, 10_000_000, "start_line")
    line_limit = _positive_limit(max_lines, 2_000, "max_lines")
    character_limit = _positive_limit(max_characters, MAX_READ_CHARACTERS, "max_characters")
    text, data = _read_utf8(selected)
    lines = text.splitlines(keepends=True)
    excerpt_lines = lines[first - 1:first - 1 + line_limit]
    excerpt = "".join(excerpt_lines)
    truncated_by_characters = len(excerpt) > character_limit
    excerpt = excerpt[:character_limit]
    visible_lines = excerpt.count("\n") + int(bool(excerpt) and not excerpt.endswith("\n"))
    end_line = first - 1 + visible_lines
    truncated = truncated_by_characters or first - 1 + len(excerpt_lines) < len(lines)
    return {
        "path": _relative_text(selected, root),
        "encoding": "utf-8",
        "sha256": hashlib.sha256(data).hexdigest(),
        "start_line": first,
        "end_line": end_line,
        "total_lines": len(lines),
        "text": excerpt,
        "truncated": truncated,
        "summary": {
            "characters": len(excerpt),
            "lines": visible_lines,
            "truncated": truncated,
        },
    }


def search_workspace(
    workspace_root: Path,
    query: str,
    directory: str = ".",
    pattern: str = "*",
    max_matches: int = 50,
    case_sensitive: bool = False,
) -> dict[str, Any]:
    root = workspace_root.resolve()
    selected = _resolve(root, directory, "directory", expect_directory=True)
    if not isinstance(query, str) or not query or len(query) > 256 or "\x00" in query:
        raise WorkspaceReadError("invalid_arguments", "query must contain 1 to 256 text characters")
    limit = _positive_limit(max_matches, MAX_SEARCH_MATCHES, "max_matches")
    if not isinstance(pattern, str) or not pattern or len(pattern) > 128:
        raise WorkspaceReadError("invalid_arguments", "pattern must contain 1 to 128 characters")
    needle = query if case_sensitive else query.casefold()
    matches: list[dict[str, Any]] = []
    scanned = 0
    skipped = 0
    truncated = False
    for path in _iter_allowed_files(root, selected):
        relative = _relative_text(path, root)
        if not fnmatch.fnmatchcase(relative.casefold(), pattern.casefold()):
            continue
        if scanned == MAX_SEARCH_FILES:
            truncated = True
            break
        scanned += 1
        try:
            text, _data = _read_utf8(path)
        except WorkspaceReadError:
            skipped += 1
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            haystack = line if case_sensitive else line.casefold()
            column = haystack.find(needle)
            if column < 0:
                continue
            if len(matches) == limit:
                truncated = True
                break
            matches.append({
                "path": relative,
                "line": number,
                "column": column + 1,
                "text": line[:500],
            })
        if truncated:
            break
    return {
        "query": query,
        "directory": _relative_text(selected, root) if selected != root else ".",
        "pattern": pattern,
        "matches": matches,
        "truncated": truncated,
        "summary": {
            "matches": len(matches),
            "files_scanned": scanned,
            "files_skipped": skipped,
            "truncated": truncated,
        },
    }
