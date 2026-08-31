from __future__ import annotations

import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bsam_agent import cli
from bsam_agent.document import SourceDocument


CURRENT_DECK = (
    b"INPUT\r\n3\r\nEND INPUT\r\n\r\n"
    b"SOLVER\r\n*type=pardiso\r\nend solver\r\nEND SOLVER\r\n"
    b"BOUNDARY\r\n*type\r\nmechanical\r\nEND BOUNDARY\r\n"
    b"CONSTITUTIVE\r\n0\r\nEND CONSTITUTIVE\r\n"
    b"MATERIALS\r\n0\r\nEND MATERIALS\r\n"
    b"CLUSTERS\r\n*type\r\nsolid\r\n*NAME\r\nply1\r\n*STOP\r\nEND CLUSTERS\r\n"
)


class SourceDocumentTests(unittest.TestCase):
    def test_no_op_round_trip_is_byte_identical(self) -> None:
        document = SourceDocument.from_bytes(CURRENT_DECK)
        self.assertEqual(CURRENT_DECK, document.render_bytes())
        self.assertTrue(document.inspection()["no_op_round_trip"])
        self.assertEqual(25, document.newline_counts()["crlf"])

    def test_required_blocks_and_cluster_commands_are_indexed(self) -> None:
        inspection = SourceDocument.from_bytes(CURRENT_DECK).inspection()
        self.assertEqual(0, inspection["summary"]["errors"])
        self.assertEqual(
            ["INPUT", "SOLVER", "BOUNDARY", "CONSTITUTIVE", "MATERIALS", "CLUSTERS"],
            [item["name"] for item in inspection["blocks"]],
        )
        self.assertEqual(["*TYPE", "*NAME", "*STOP"], [item["command"] for item in inspection["cluster_commands"]])

    def test_obsolete_tokens_are_diagnostics_only(self) -> None:
        raw = CURRENT_DECK.replace(b"MATERIALS\r\n", b"MATERIAL\r\n", 1)
        inspection = SourceDocument.from_bytes(raw).inspection()
        codes = [item["code"] for item in inspection["diagnostics"]]
        self.assertIn("BSAM-E100", codes)
        self.assertIn("BSAM-W110", codes)

    def test_statistical_long_heading_matches_first_list_field(self) -> None:
        raw = CURRENT_DECK + b"STATISTICAL DISTRIBUTIONS\r\nEND STATISTICAL DISTRIBUTIONS\r\n"
        inspection = SourceDocument.from_bytes(raw).inspection()
        self.assertIn("STATISTICAL", [item["name"] for item in inspection["blocks"]])
        self.assertIn("BSAM-W110", [item["code"] for item in inspection["diagnostics"]])

    def test_baseline_command_is_runnable(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            status = cli.main(["baseline"])
        self.assertEqual(0, status)
        value = json.loads(output.getvalue())
        self.assertEqual("9954027f1c325c63d58aeb836e8fec41a4b363af", value["source_commit"])


if __name__ == "__main__":
    unittest.main()
