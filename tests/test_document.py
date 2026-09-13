from __future__ import annotations

import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bsam_agent import cli
from bsam_agent.document import Diagnostic, SourceDocument


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
        by_code = {item["code"]: item for item in inspection["diagnostics"]}
        self.assertEqual("structure", by_code["BSAM-E100"]["level"])
        self.assertEqual("syntax", by_code["BSAM-W110"]["level"])
        self.assertEqual("source-defined", by_code["BSAM-W110"]["provenance"])
        self.assertEqual({"structure": 1, "syntax": 1}, inspection["summary"]["by_level"])

    def test_new_diagnostic_codes_require_explicit_level_and_provenance(self) -> None:
        with self.assertRaisesRegex(ValueError, "requires explicit"):
            Diagnostic("BSAM-W999", "warning", "new diagnostic")
        diagnostic = Diagnostic(
            "BSAM-W999", "warning", "review this estimate",
            level="engineering-plausibility", provenance="engineering-heuristic",
        )
        self.assertEqual("engineering-plausibility", diagnostic.as_dict()["level"])

    def test_statistical_long_heading_matches_first_list_field(self) -> None:
        raw = CURRENT_DECK + b"STATISTICAL DISTRIBUTIONS\r\nEND STATISTICAL DISTRIBUTIONS\r\n"
        inspection = SourceDocument.from_bytes(raw).inspection()
        self.assertIn("STATISTICAL", [item["name"] for item in inspection["blocks"]])
        self.assertIn("BSAM-W110", [item["code"] for item in inspection["diagnostics"]])

    def test_registered_obsolete_and_compatibility_tokens_emit_replacements(self) -> None:
        raw = (
            CURRENT_DECK
            .replace(b"SOLVER\r\n", b"SOLVE\r\n", 1)
            .replace(b"MATERIALS\r\n", b"MATERIAL\r\n", 1)
            .replace(b"CLUSTERS\r\n", b"APPROXIMATION\r\n", 1)
            .replace(b"END CLUSTERS\r\n", b"END APPROXIMATION\r\n", 1)
        )
        diagnostics = SourceDocument.from_bytes(raw).inspection()["diagnostics"]
        replacements = {
            (item.get("replacement"), item["code"])
            for item in diagnostics if item["code"].startswith("BSAM-W11")
        }
        self.assertEqual(
            {
                ("SOLVER", "BSAM-W110"),
                ("MATERIALS", "BSAM-W110"),
                ("CLUSTERS", "BSAM-W110"),
                ("END CLUSTERS", "BSAM-W111"),
            },
            replacements,
        )

    def test_repeated_top_level_block_warning_is_classified(self) -> None:
        raw = CURRENT_DECK + b"SOLVER\r\nEND SOLVER\r\n"
        diagnostics = SourceDocument.from_bytes(raw).inspection()["diagnostics"]
        warning = next(item for item in diagnostics if item["code"] == "BSAM-W120")
        self.assertEqual("warning", warning["severity"])
        self.assertEqual("structure", warning["level"])
        self.assertEqual("documentation-defined", warning["provenance"])

    def test_baseline_command_is_runnable(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            status = cli.main(["baseline"])
        self.assertEqual(0, status)
        value = json.loads(output.getvalue())
        self.assertEqual("9954027f1c325c63d58aeb836e8fec41a4b363af", value["source_commit"])


if __name__ == "__main__":
    unittest.main()
