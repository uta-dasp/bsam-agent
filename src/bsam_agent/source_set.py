"""Lossless BSAM source sets and finite-element include graphs."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Any

from .document import Diagnostic, SourceDocument, SourceLine
from .semantic import SemanticIndex, build_semantic_index


@dataclass(frozen=True)
class IncludeReference:
    source: Path
    line: int
    spelling: str | None
    target: Path | None
    status: str
    depth: int

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "source": str(self.source),
            "line": self.line,
            "spelling": self.spelling,
            "status": self.status,
            "depth": self.depth,
        }
        if self.target is not None:
            result["target"] = str(self.target)
        return result


def _include_spelling(line: SourceLine) -> tuple[bool, str | None]:
    """Return whether a line dispatches *INCL and its last FILE value.

    The local parser reads a 240-character command record, splits it on
    commas, recognizes command and option prefixes case-insensitively, and
    retains at most 80 characters for an option value.
    """
    record = line.text[:240]
    if not record.startswith("*") or record.startswith("**"):
        return False, None
    fields = record.split(",")
    if not fields[0].upper().startswith("*INCL"):
        return False, None
    value: str | None = None
    for field in fields[1:]:
        if "=" not in field:
            continue
        keyword, candidate = field.split("=", 1)
        if keyword.strip().upper()[:3] == "FIL":
            value = candidate.lstrip()[:80].rstrip()
    return True, value


class SourceSet:
    """A root deck plus byte-preserved FE include files and graph edges."""

    def __init__(self, root: Path, workspace_root: Path) -> None:
        self.root = root
        self.input_directory = root.parent
        self.workspace_root = workspace_root
        self.documents: dict[Path, SourceDocument] = {}
        self.references: list[IncludeReference] = []
        self._graph_diagnostics: list[Diagnostic] = []

    @classmethod
    def read(cls, root: Path, workspace_root: Path | None = None) -> "SourceSet":
        root = root.resolve()
        if not root.is_file():
            raise FileNotFoundError(f"input deck not found: {root}")
        boundary = (workspace_root or root.parent).resolve()
        if not boundary.is_dir():
            raise ValueError(f"workspace root is not a directory: {boundary}")
        if not root.is_relative_to(boundary):
            raise ValueError(f"input deck is outside workspace root: {root}")
        result = cls(root, boundary)
        result._load(root, ancestry=(), depth=0)
        return result

    def _candidate_lines(self, path: Path, document: SourceDocument) -> list[SourceLine]:
        if path != self.root:
            result: list[SourceLine] = []
            for line in document.lines:
                result.append(line)
                if line.text[:5].upper() == "*STOP":
                    break
            return result
        result: list[SourceLine] = []
        for block in document.blocks():
            if block["name"] != "CLUSTERS":
                continue
            final = block["end_line"] or len(document.lines)
            result.extend(document.lines[block["start_line"]:final])
        return result

    @staticmethod
    def _has_unsupported_path_form(spelling: str) -> bool:
        windows = PureWindowsPath(spelling)
        return (
            windows.is_absolute()
            or bool(windows.drive)
            or spelling.startswith(("/", "\\"))
            or spelling[:1] in {"'", '"'}
            or spelling[-1:] in {"'", '"'}
        )

    def _diagnostic(
        self,
        code: str,
        message: str,
        source: Path,
        line: int,
    ) -> None:
        self._graph_diagnostics.append(Diagnostic(
            code=code,
            severity="error",
            message=message,
            line=line,
            source=str(source),
        ))

    def _load(self, path: Path, ancestry: tuple[Path, ...], depth: int) -> None:
        document = SourceDocument.read(path)
        self.documents[path] = document
        active_ancestry = (*ancestry, path)
        for line in self._candidate_lines(path, document):
            is_include, spelling = _include_spelling(line)
            if not is_include:
                continue
            if spelling is None or not spelling:
                self.references.append(IncludeReference(
                    path, line.number, spelling, None, "missing-file-option", depth
                ))
                self._diagnostic(
                    "BSAM-E200",
                    "*INCLUDE requires a non-empty FILE option",
                    path,
                    line.number,
                )
                continue
            if self._has_unsupported_path_form(spelling):
                self.references.append(IncludeReference(
                    path, line.number, spelling, None, "unsupported-path", depth
                ))
                self._diagnostic(
                    "BSAM-E201",
                    f"include path uses an unsupported absolute, drive-qualified, or quoted form: {spelling}",
                    path,
                    line.number,
                )
                continue

            # BSAM prepends the original input directory even for nested
            # includes; it does not resolve relative to the including file.
            target = (self.input_directory / spelling).resolve()
            if not target.is_relative_to(self.workspace_root):
                self.references.append(IncludeReference(
                    path, line.number, spelling, target, "outside-workspace", depth
                ))
                self._diagnostic(
                    "BSAM-E202",
                    f"include target escapes the configured workspace root: {spelling}",
                    path,
                    line.number,
                )
                continue
            if not target.is_file():
                self.references.append(IncludeReference(
                    path, line.number, spelling, target, "missing", depth
                ))
                self._diagnostic(
                    "BSAM-E203",
                    f"include target was not found relative to the input directory: {spelling}",
                    path,
                    line.number,
                )
                continue
            if target in active_ancestry:
                self.references.append(IncludeReference(
                    path, line.number, spelling, target, "cycle", depth
                ))
                cycle = " -> ".join(item.name for item in (*active_ancestry, target))
                self._diagnostic(
                    "BSAM-E204",
                    f"include cycle is blocked by the agent: {cycle}",
                    path,
                    line.number,
                )
                continue
            if target in self.documents:
                self.references.append(IncludeReference(
                    path, line.number, spelling, target, "already-loaded", depth
                ))
                continue
            self.references.append(IncludeReference(
                path, line.number, spelling, target, "resolved", depth
            ))
            self._load(target, active_ancestry, depth + 1)

    @property
    def sha256(self) -> str:
        return self.digest_with()

    def digest_with(self, replacements: dict[Path, bytes] | None = None) -> str:
        """Digest the source set, optionally substituting exact file bytes."""
        replacements = replacements or {}
        digest = hashlib.sha256()
        labels = {
            path: (
                "<root>"
                if path == self.root
                else os.path.relpath(path, self.input_directory).replace("\\", "/")
            )
            for path in self.documents
        }
        for path in sorted(self.documents, key=lambda item: labels[item].casefold()):
            relative = labels[path]
            raw = replacements.get(path, self.documents[path].raw)
            digest.update(relative.encode("utf-8"))
            digest.update(b"\0")
            digest.update(len(raw).to_bytes(8, "big"))
            digest.update(raw)
        return digest.hexdigest().upper()

    def render_files(self) -> dict[Path, bytes]:
        """Render every unchanged source file byte-for-byte."""
        return {path: document.render_bytes() for path, document in self.documents.items()}

    def diagnostics(self) -> list[Diagnostic]:
        root_diagnostics = [Diagnostic(
            code=item.code,
            severity=item.severity,
            message=item.message,
            line=item.line,
            replacement=item.replacement,
            source=str(self.root),
        ) for item in self.documents[self.root].diagnostics()]
        return [*root_diagnostics, *self._graph_diagnostics]

    def semantic_index(self) -> SemanticIndex:
        sources = []
        for path, document in self.documents.items():
            relative = "<root>" if path == self.root else os.path.relpath(
                path, self.input_directory
            ).replace("\\", "/")
            sources.append((path, relative, self._candidate_lines(path, document)))
        return build_semantic_index(sources)

    def inspection(self) -> dict[str, Any]:
        root_inspection = self.documents[self.root].inspection()
        diagnostics = self.diagnostics()
        semantic_index = self.semantic_index()
        files = []
        for path, document in self.documents.items():
            files.append({
                "path": str(path),
                "relative_path": str(path.relative_to(self.workspace_root)),
                "role": "root" if path == self.root else "include",
                "sha256": document.sha256,
                "size_bytes": len(document.raw),
                "line_count": len(document.lines),
                "newline_counts": document.newline_counts(),
                "no_op_round_trip": document.render_bytes() == document.raw,
            })
        root_inspection.update({
            "source_set_sha256": self.sha256,
            "no_op_round_trip": all(
                document.render_bytes() == document.raw
                for document in self.documents.values()
            ),
            "source_set": {
                "root": str(self.root),
                "input_directory": str(self.input_directory),
                "workspace_root": str(self.workspace_root),
                "files": files,
                "include_references": [item.as_dict() for item in self.references],
            },
            "semantic_model": semantic_index.as_dict(),
            "diagnostics": [item.as_dict() for item in diagnostics],
            "summary": {
                "errors": sum(item.severity == "error" for item in diagnostics),
                "warnings": sum(item.severity == "warning" for item in diagnostics),
            },
        })
        return root_inspection
