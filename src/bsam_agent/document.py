"""Lossless BSAM source document and conservative structural inspection."""

from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .registry import load_registry


@dataclass(frozen=True)
class SourceLine:
    number: int
    start: int
    end: int
    content: bytes
    newline: bytes

    @property
    def text(self) -> str:
        # Latin-1 is deliberately one byte per code point. It is an inspection
        # view; rendering always uses the retained original bytes.
        return self.content.decode("latin-1")

    @property
    def stripped(self) -> str:
        return self.text.strip()

    @property
    def first_field(self) -> str:
        """Return the first whitespace/comma-delimited list-directed field."""
        value = self.text.lstrip()
        end = 0
        while end < len(value) and not value[end].isspace() and value[end] != ",":
            end += 1
        return value[:end]


@dataclass(frozen=True)
class Diagnostic:
    code: str
    severity: str
    message: str
    line: int | None = None
    replacement: str | None = None
    source: str | None = None

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
        }
        if self.line is not None:
            result["line"] = self.line
        if self.replacement is not None:
            result["replacement"] = self.replacement
        if self.source is not None:
            result["source"] = self.source
        return result


def _split_line(raw_line: bytes) -> tuple[bytes, bytes]:
    if raw_line.endswith(b"\r\n"):
        return raw_line[:-2], b"\r\n"
    if raw_line.endswith((b"\n", b"\r")):
        return raw_line[:-1], raw_line[-1:]
    return raw_line, b""


class SourceDocument:
    """A byte-preserving source with a conservative current-syntax index."""

    def __init__(self, source_name: str, raw: bytes) -> None:
        self.source_name = source_name
        self.raw = raw
        self.lines = self._make_lines(raw)

    @classmethod
    def read(cls, path: Path) -> "SourceDocument":
        return cls(str(path.resolve()), path.read_bytes())

    @classmethod
    def from_bytes(cls, raw: bytes, source_name: str = "<memory>") -> "SourceDocument":
        return cls(source_name, raw)

    @staticmethod
    def _make_lines(raw: bytes) -> tuple[SourceLine, ...]:
        result: list[SourceLine] = []
        offset = 0
        for number, raw_line in enumerate(raw.splitlines(keepends=True), start=1):
            content, newline = _split_line(raw_line)
            end = offset + len(raw_line)
            result.append(SourceLine(number, offset, end, content, newline))
            offset = end
        if raw and offset < len(raw):
            content = raw[offset:]
            result.append(SourceLine(len(result) + 1, offset, len(raw), content, b""))
        return tuple(result)

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.raw).hexdigest().upper()

    def render_bytes(self) -> bytes:
        """Render an unchanged source byte-for-byte."""
        return self.raw

    def newline_counts(self) -> dict[str, int]:
        counts = Counter(line.newline for line in self.lines)
        return {
            "crlf": counts[b"\r\n"],
            "lf": counts[b"\n"],
            "cr": counts[b"\r"],
            "none": counts[b""],
        }

    def _block_starts(self) -> list[tuple[int, str]]:
        registry = load_registry()
        names = {item["canonical"] for item in registry["top_level_blocks"]}
        return [
            (line.number, line.first_field)
            for line in self.lines
            if line.first_field in names
        ]

    def blocks(self) -> list[dict[str, Any]]:
        starts = self._block_starts()
        result: list[dict[str, Any]] = []
        for index, (line_number, name) in enumerate(starts):
            next_start = starts[index + 1][0] if index + 1 < len(starts) else len(self.lines) + 1
            canonical_end = f"END {name}"
            accepted_ends = {canonical_end}
            if name == "STATISTICAL":
                accepted_ends = {"END STATISTICAL DISTRIBUTIONS"}
            if name == "CLUSTERS":
                accepted_ends.add("END APPROXIMATION")
            end_line = next(
                (line.number for line in self.lines[line_number:next_start - 1] if line.stripped in accepted_ends),
                None,
            )
            result.append({"name": name, "start_line": line_number, "end_line": end_line})
        return result

    def cluster_commands(self) -> list[dict[str, Any]]:
        registry = load_registry()
        known = {item["dispatch_prefix"].upper(): item["canonical"] for item in registry["cluster_commands"]}
        cluster_spans = [item for item in self.blocks() if item["name"] == "CLUSTERS"]
        result: list[dict[str, Any]] = []
        for span in cluster_spans:
            final = span["end_line"] or len(self.lines)
            for line in self.lines[span["start_line"]:final]:
                stripped = line.stripped
                if not stripped.startswith("*") or stripped.startswith("**"):
                    continue
                prefix = stripped[:5].upper()
                if prefix in known:
                    result.append({"command": known[prefix], "line": line.number})
        return result

    def diagnostics(self) -> list[Diagnostic]:
        registry = load_registry()
        block_names = [name for _, name in self._block_starts()]
        diagnostics: list[Diagnostic] = []
        for block in registry["top_level_blocks"]:
            if block["required"] and block["canonical"] not in block_names:
                diagnostics.append(Diagnostic(
                    code="BSAM-E100",
                    severity="error",
                    message=f"required exact top-level block {block['canonical']} was not found",
                ))

        obsolete = {item["token"]: item for item in registry["obsolete_tokens"]}
        for line in self.lines:
            record = obsolete.get(line.stripped)
            if record is None:
                continue
            replacement = record["replacement"]
            compatibility = record["behavior"] == "accepted-compatibility"
            message = (
                f"compatibility token {line.stripped} is accepted; current generation uses {replacement}"
                if compatibility
                else f"obsolete top-level token {line.stripped}; current generation uses {replacement}"
            )
            diagnostics.append(Diagnostic(
                code=record["diagnostic"],
                severity="warning",
                line=line.number,
                replacement=replacement,
                message=message,
            ))

        counts = Counter(block_names)
        for name, count in counts.items():
            if count > 1:
                diagnostics.append(Diagnostic(
                    code="BSAM-W120",
                    severity="warning",
                    message=f"top-level block {name} occurs {count} times; semantic support for repeated blocks is not established",
                ))
        return diagnostics

    def inspection(self) -> dict[str, Any]:
        diagnostics = self.diagnostics()
        return {
            "source": self.source_name,
            "sha256": self.sha256,
            "size_bytes": len(self.raw),
            "line_count": len(self.lines),
            "inspection_encoding": "latin-1-byte-preserving",
            "newline_counts": self.newline_counts(),
            "no_op_round_trip": self.render_bytes() == self.raw,
            "blocks": self.blocks(),
            "cluster_commands": self.cluster_commands(),
            "diagnostics": [item.as_dict() for item in diagnostics],
            "summary": {
                "errors": sum(item.severity == "error" for item in diagnostics),
                "warnings": sum(item.severity == "warning" for item in diagnostics),
            },
        }
