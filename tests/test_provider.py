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
    override_provider_config,
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

    def test_openai_configuration_requires_official_endpoint_and_store_false(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "provider.json"
            base = {
                "provider": "openai", "model": "test",
                "endpoint": "https://api.openai.com",
                "credential_reference": "env:OPENAI_API_KEY",
                "data_policy": "sanitized", "store": False,
                "reasoning_effort": "high",
            }
            path.write_text(json.dumps(base), encoding="utf-8")
            loaded = load_provider_config(path)
            self.assertFalse(loaded.store)
            self.assertEqual("high", loaded.reasoning_effort)

            for changes in (
                {"store": True},
                {"endpoint": "https://example.com"},
                {"data_policy": "local-private"},
                {"credential_reference": None},
                {"credential_reference": "env:OTHER_KEY"},
                {"reasoning_effort": "extreme"},
            ):
                path.write_text(json.dumps(base | changes), encoding="utf-8")
                with self.subTest(changes=changes), self.assertRaises(ProviderConfigError):
                    load_provider_config(path)

    def test_provider_switching_uses_safe_transport_defaults(self) -> None:
        local = load_provider_config(Path(__file__).resolve().parents[1] / "config" / "provider.local.example.json")
        hosted = override_provider_config(
            local, provider="openai", model="gpt-5.6-sol", reasoning_effort="high",
        )
        self.assertEqual("openai", hosted.provider)
        self.assertEqual("gpt-5.6-sol", hosted.model)
        self.assertEqual("env:OPENAI_API_KEY", hosted.credential_reference)
        self.assertEqual("https://api.openai.com", hosted.endpoint)
        self.assertEqual("sanitized", hosted.data_policy)
        self.assertFalse(hosted.store)

        local_again = override_provider_config(hosted, provider="cpu-local")
        self.assertEqual("cpu-local", local_again.provider)
        self.assertEqual("Meta-Llama-3.1-8B-Instruct-Q4_K_M", local_again.model)
        self.assertEqual("http://127.0.0.1:18080", local_again.endpoint)
        self.assertEqual("env:BSAM_LOCAL_API_KEY", local_again.credential_reference)
        self.assertEqual("local-private", local_again.data_policy)
        self.assertIsNone(local_again.reasoning_effort)


if __name__ == "__main__":
    unittest.main()
