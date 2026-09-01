from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bsam_agent.api import ApiError, LocalAgentApi, build_server


DECK = (
    b"INPUT\n3\nEND INPUT\n"
    b"BOUNDARY\n*type\nmechanical\n*convergence\nabsolute=1\nEND BOUNDARY\n"
    b"CONSTITUTIVE\n0\nEND CONSTITUTIVE\n"
    b"MATERIALS\n0\nEND MATERIALS\n"
    b"CLUSTERS\n*type\nsolid\n*STOP\nEND CLUSTERS\n"
)


class LocalApiTests(unittest.TestCase):
    def test_dispatch_enforces_workspace_schemas_and_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.in").write_bytes(DECK)
            api = LocalAgentApi(root)

            validation = api.dispatch("validate_model", {"source": "model.in"})
            self.assertEqual(0, validation["summary"]["errors"])
            plan = api.dispatch("preview_parameter_change", {
                "source": "model.in",
                "block": "BOUNDARY",
                "construct": "CONVERGENCE",
                "parameter": "absolute",
                "value": "2",
                "plan_path": "change.json",
            })
            self.assertTrue((root / "change.json").is_file())
            self.assertEqual(plan["plan_id"], api.dispatch(
                "review_change", {"plan_path": "change.json"}
            )["plan_id"])
            with self.assertRaisesRegex(ApiError, "confirm=true"):
                api.dispatch("apply_change", {
                    "plan_path": "change.json", "destination": "changed.in", "confirm": False,
                })
            result = api.dispatch("apply_change", {
                "plan_path": "change.json", "destination": "changed.in", "confirm": True,
            })
            self.assertEqual(0, result["validation"]["summary"]["errors"])
            with self.assertRaisesRegex(ApiError, "escapes"):
                api.dispatch("validate_model", {"source": "../outside.in"})
            with self.assertRaisesRegex(ApiError, "unknown arguments"):
                api.dispatch("validate_model", {"source": "model.in", "extra": True})

    def test_http_server_is_loopback_and_returns_json_errors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.in").write_bytes(DECK)
            server = build_server(LocalAgentApi(root), 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            port = server.server_address[1]
            try:
                with urlopen(f"http://127.0.0.1:{port}/api/v1/health") as response:
                    health = json.load(response)
                self.assertEqual("ok", health["status"])
                self.assertEqual("127.0.0.1", server.server_address[0])

                request = Request(
                    f"http://127.0.0.1:{port}/api/v1/tools/validate_model",
                    data=json.dumps({"source": "model.in", "bad": 1}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with self.assertRaises(HTTPError) as raised:
                    urlopen(request)
                error = json.loads(raised.exception.read())
                self.assertEqual("invalid_arguments", error["error"]["code"])
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
