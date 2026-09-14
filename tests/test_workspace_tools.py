from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bsam_agent.api import ApiError, LocalAgentApi


class WorkspaceToolTests(unittest.TestCase):
    def test_list_read_and_literal_search_are_bounded_and_filtered(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "docs").mkdir()
            (root / ".git").mkdir()
            (root / ".private").mkdir()
            (root / "model.in").write_text("INPUT\n3\nEND INPUT\n", encoding="utf-8")
            (root / "docs" / "notes.md").write_text(
                "Convergence warning\nSecond line\n", encoding="utf-8",
            )
            (root / ".git" / "hidden.md").write_text("warning", encoding="utf-8")
            (root / ".private" / "hidden.md").write_text("warning", encoding="utf-8")
            (root / ".env").write_text("TOKEN=not-for-tools", encoding="utf-8")
            (root / "script.py").write_text("warning", encoding="utf-8")
            api = LocalAgentApi(root)

            listed = api.dispatch("list_workspace_files", {"max_files": 10})
            read = api.dispatch("read_allowed_text_file", {
                "path": "docs/notes.md", "max_lines": 1, "max_characters": 100,
            })
            searched = api.dispatch("search_workspace", {
                "query": "warning", "pattern": "*.md", "max_matches": 10,
            })

        self.assertEqual(["docs/notes.md", "model.in"], [item["path"] for item in listed["files"]])
        self.assertEqual(["Convergence warning"], read["text"].splitlines())
        self.assertTrue(read["truncated"])
        self.assertEqual(64, len(read["sha256"]))
        self.assertEqual(["docs/notes.md"], [item["path"] for item in searched["matches"]])
        self.assertEqual(1, searched["matches"][0]["line"])

    def test_sensitive_disallowed_and_escaping_paths_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env").write_text("TOKEN=value", encoding="utf-8")
            (root / "model.py").write_text("print('no')", encoding="utf-8")
            api = LocalAgentApi(root)

            cases = (
                ({"path": ".env"}, "path_not_allowed"),
                ({"path": "model.py"}, "unsupported_file"),
                ({"path": "../outside.md"}, "path_not_allowed"),
            )
            for arguments, expected in cases:
                with self.subTest(arguments=arguments), self.assertRaises(ApiError) as raised:
                    api.dispatch("read_allowed_text_file", arguments)
                self.assertEqual(expected, raised.exception.code)

    def test_symbolic_links_are_never_followed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "target.md"
            target.write_text("engineering note", encoding="utf-8")
            link = root / "linked.md"
            try:
                os.symlink(target, link)
            except (OSError, NotImplementedError):
                self.skipTest("symbolic links are unavailable for this test user")
            api = LocalAgentApi(root)

            with self.assertRaises(ApiError) as raised:
                api.dispatch("read_allowed_text_file", {"path": "linked.md"})

        self.assertEqual("path_not_allowed", raised.exception.code)

    def test_limits_and_unknown_arguments_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "notes.md").write_text("note", encoding="utf-8")
            api = LocalAgentApi(root)

            with self.assertRaises(ApiError) as zero:
                api.dispatch("list_workspace_files", {"max_files": 0})
            with self.assertRaises(ApiError) as unknown:
                api.dispatch("search_workspace", {"query": "note", "regex": True})

        self.assertEqual("invalid_arguments", zero.exception.code)
        self.assertEqual("invalid_arguments", unknown.exception.code)

    def test_listing_and_search_results_have_stable_lexical_order(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "zeta.md").write_text("literal [marker]", encoding="utf-8")
            (root / "alpha.md").write_text("literal [marker]", encoding="utf-8")
            (root / "middle").mkdir()
            (root / "middle" / "note.md").write_text("literal [marker]", encoding="utf-8")
            api = LocalAgentApi(root)

            listed = api.dispatch("list_workspace_files", {"max_files": 2})
            searched = api.dispatch("search_workspace", {
                "query": "[marker]", "pattern": "*.md", "max_matches": 10,
            })

        self.assertEqual(["alpha.md", "middle/note.md"], [item["path"] for item in listed["files"]])
        self.assertTrue(listed["truncated"])
        self.assertEqual(
            ["alpha.md", "middle/note.md", "zeta.md"],
            [item["path"] for item in searched["matches"]],
        )

    def test_binary_oversized_and_invalid_utf8_content_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "binary.log").write_bytes(b"before\x00after")
            (root / "oversized.log").write_bytes(b"x" * 1_048_577)
            (root / "invalid.log").write_bytes(b"\xff\xfe")
            api = LocalAgentApi(root)

            cases = (
                ("binary.log", "unsupported_file"),
                ("oversized.log", "file_too_large"),
                ("invalid.log", "unsupported_encoding"),
            )
            for path, expected in cases:
                with self.subTest(path=path), self.assertRaises(ApiError) as raised:
                    api.dispatch("read_allowed_text_file", {"path": path})
                self.assertEqual(expected, raised.exception.code)


if __name__ == "__main__":
    unittest.main()
