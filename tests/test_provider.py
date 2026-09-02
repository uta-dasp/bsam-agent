from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bsam_agent.provider import (
    Message,
    ProviderConfigError,
    ProviderRequest,
    ProviderResponse,
    ToolCall,
    Usage,
    load_provider_config,
)


class ProviderBoundaryTests(unittest.TestCase):
    def test_provider_types_contain_no_vendor_objects(self) -> None:
        request = ProviderRequest(
            messages=(Message("user", "Validate the model"),),
            tools={"validate_model": {"type": "object"}},
            response_schema=None,
            max_output_tokens=128,
            correlation_id="case-1",
            data_policy="synthetic-only",
        )
        response = ProviderResponse(
            tool_calls=(ToolCall("call-1", "validate_model", {"source": "model.in"}),),
            usage=Usage(10, 5),
        )
        self.assertEqual("user", request.messages[0].role)
        self.assertEqual("validate_model", response.tool_calls[0].name)

    def test_local_configuration_is_strict_loopback_and_secret_free(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "provider.json"
            path.write_text(json.dumps({
                "provider": "cpu-local", "model": "test",
                "endpoint": "http://127.0.0.1:8080", "data_policy": "local-private",
            }), encoding="utf-8")
            self.assertEqual("test", load_provider_config(path).model)

            path.write_text(json.dumps({
                "provider": "cpu-local", "model": "test",
                "endpoint": "http://example.com", "api_key": "forbidden",
            }), encoding="utf-8")
            with self.assertRaises(ProviderConfigError):
                load_provider_config(path)

            path.write_text(json.dumps({
                "provider": "cpu-local", "model": "test",
                "endpoint": "https://127.0.0.1:8080/v1",
            }), encoding="utf-8")
            with self.assertRaises(ProviderConfigError):
                load_provider_config(path)


if __name__ == "__main__":
    unittest.main()
