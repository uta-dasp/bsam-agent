from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bsam_agent import cli
from bsam_agent.source_set import SourceSet


def root_deck(cluster_lines: bytes) -> bytes:
    return (
        b"INPUT\r\n3\r\nEND INPUT\r\n"
        b"BOUNDARY\r\n*type\r\nmechanical\r\nEND BOUNDARY\r\n"
        b"CONSTITUTIVE\r\n0\r\nEND CONSTITUTIVE\r\n"
        b"MATERIALS\r\n0\r\nEND MATERIALS\r\n"
        b"CLUSTERS\r\n*type\r\nsolid\r\n"
        + cluster_lines
        + b"*STOP\r\nEND CLUSTERS\r\n"
    )


class SourceSetTests(unittest.TestCase):
    def test_nested_includes_resolve_from_original_input_directory_and_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            parts = root / "parts"
            parts.mkdir()
            deck = root / "model.in"
            mesh = parts / "mesh.inc"
            shared = root / "shared.inc"
            deck_bytes = root_deck(b"*INCLUDE, FILE=parts/mesh.inc\r\n")
            mesh_bytes = b"*NODE\n1, 0.0, 0.0, 0.0\n*INCLUDE, FILE=shared.inc\n"
            shared_bytes = b"*NSET, NSET=all\r1\r"
            deck.write_bytes(deck_bytes)
            mesh.write_bytes(mesh_bytes)
            shared.write_bytes(shared_bytes)

            source_set = SourceSet.read(deck)
            rendered = source_set.render_files()
            inspection = source_set.inspection()

            self.assertEqual({deck.resolve(), mesh.resolve(), shared.resolve()}, set(rendered))
            self.assertEqual(deck_bytes, rendered[deck.resolve()])
            self.assertEqual(mesh_bytes, rendered[mesh.resolve()])
            self.assertEqual(shared_bytes, rendered[shared.resolve()])
            self.assertTrue(inspection["no_op_round_trip"])
            self.assertEqual(3, len(inspection["source_set"]["files"]))
            self.assertEqual(0, inspection["summary"]["errors"])
            nested = inspection["source_set"]["include_references"][1]
            self.assertEqual(str(shared.resolve()), nested["target"])
            self.assertEqual("resolved", nested["status"])
            self.assertEqual(1, nested["depth"])

            renamed = root / "renamed.in"
            renamed.write_bytes(deck_bytes)
            self.assertEqual(source_set.sha256, SourceSet.read(renamed).sha256)

            original_digest = source_set.sha256
            shared.write_bytes(shared_bytes + b"** retained comment\r")
            self.assertNotEqual(original_digest, SourceSet.read(deck).sha256)

    def test_cycle_missing_file_malformed_and_workspace_escape_are_errors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "workspace"
            workspace.mkdir()
            outside = Path(directory) / "outside.inc"
            outside.write_text("*NODE\n", encoding="ascii")
            deck = workspace / "model.in"
            a = workspace / "a.inc"
            b = workspace / "b.inc"
            deck.write_bytes(root_deck(
                b"*INCLUDE\r\n"
                b"*INCLUDE, FILE=\"quoted.inc\"\r\n"
                b"*INCLUDE, FILE=missing.inc\r\n"
                b"*INCLUDE, FILE=../outside.inc\r\n"
                b"*INCLUDE, FILE=a.inc\r\n"
            ))
            a.write_text("*INCLUDE, FILE=b.inc\n", encoding="ascii")
            b.write_text("*INCLUDE, FILE=a.inc\n", encoding="ascii")

            inspection = SourceSet.read(deck, workspace).inspection()
            codes = {item["code"] for item in inspection["diagnostics"]}
            statuses = {
                item["status"]
                for item in inspection["source_set"]["include_references"]
            }

            self.assertTrue({"BSAM-E200", "BSAM-E201", "BSAM-E202", "BSAM-E203", "BSAM-E204"} <= codes)
            self.assertTrue({
                "missing-file-option",
                "unsupported-path",
                "outside-workspace",
                "missing",
                "cycle",
            } <= statuses)
            for diagnostic in inspection["diagnostics"]:
                self.assertIn("source", diagnostic)

    def test_root_include_scan_is_limited_to_clusters_and_cli_validate_blocks_graph_errors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            deck = root / "model.in"
            raw = root_deck(b"*INCLUDE, FILE=missing.inc\r\n")
            raw = raw.replace(
                b"mechanical\r\n",
                b"mechanical\r\n*INCLUDE, FILE=not-fe.inc\r\n",
            )
            deck.write_bytes(raw)

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                status = cli.main(["validate", str(deck), "--compact"])
            result = json.loads(stdout.getvalue())

            self.assertEqual(2, status)
            self.assertEqual(64, len(result["source_set_sha256"]))
            self.assertEqual(1, result["summary"]["errors"])
            self.assertEqual("BSAM-E203", result["diagnostics"][0]["code"])
            source_set = SourceSet.read(deck)
            self.assertEqual(1, len(source_set.references))

    def test_include_references_after_fragment_stop_are_not_reachable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            deck = root / "model.in"
            fragment = root / "fragment.inc"
            deck.write_bytes(root_deck(b"*INCLUDE, FILE=fragment.inc\r\n"))
            fragment.write_text(
                "*NODE\n1, 0, 0, 0\n*STOP\n*INCLUDE, FILE=missing.inc\n",
                encoding="ascii",
            )

            source_set = SourceSet.read(deck)

            self.assertEqual(1, len(source_set.references))
            self.assertEqual(0, source_set.inspection()["summary"]["errors"])


if __name__ == "__main__":
    unittest.main()
