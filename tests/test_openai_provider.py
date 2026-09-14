from __future__ import annotations

import io
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bsam_agent.local_provider import ProviderError
from bsam_agent.api import LocalAgentApi
from bsam_agent.openai_provider import OpenAIResponsesProvider
from bsam_agent.orchestrator import ChatOrchestrator
from bsam_agent.provider import Message, ProviderConfig, ProviderRequest
from bsam_agent.provider_factory import create_provider
from bsam_agent.tool_contracts import TOOL_CONTRACTS


def config() -> ProviderConfig:
    return ProviderConfig(
        "openai", "test-model", "https://api.openai.com", "env:OPENAI_API_KEY",
        2.0, 24000, 128, "sanitized", False, "high",
    )


def request(*, with_tools: bool = False) -> ProviderRequest:
    return ProviderRequest(
        messages=(Message("system", "Route safely"), Message("user", "Validate model.in")),
        tools=(
            {"validate_model": TOOL_CONTRACTS["validate_model"].request_schema()}
            if with_tools else {}
        ),
        response_schema=None if with_tools else {
            "type": "object", "additionalProperties": False,
            "required": ["ok"], "properties": {"ok": {"type": "boolean"}},
        },
        max_output_tokens=64,
        correlation_id="hosted-1",
        data_policy="sanitized",
    )


class _Response:
    def __init__(self, value: dict[str, object]) -> None:
        self._raw = json.dumps(value).encode("utf-8")

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._raw


class OpenAIProviderTests(unittest.TestCase):
    @patch("bsam_agent.openai_provider.urlopen")
    def test_uses_responses_api_store_false_and_json_mode(self, mocked: object) -> None:
        mocked.return_value = _Response({  # type: ignore[attr-defined]
            "status": "completed",
            "output": [{
                "type": "message",
                "content": [{"type": "output_text", "text": '{"ok":true}'}],
            }],
            "usage": {"input_tokens": 12, "output_tokens": 4},
        })
        response = OpenAIResponsesProvider(
            config(), credential_resolver=lambda _reference: "test-secret"
        ).complete(request())

        call = mocked.call_args.args[0]  # type: ignore[attr-defined]
        payload = json.loads(call.data)
        self.assertEqual("https://api.openai.com/v1/responses", call.full_url)
        self.assertIs(payload["store"], False)
        self.assertEqual({"effort": "high"}, payload["reasoning"])
        self.assertEqual({"type": "json_object"}, payload["text"]["format"])
        self.assertIn("Required response JSON Schema", payload["input"][0]["content"])
        self.assertIn('"ok"', payload["input"][0]["content"])
        self.assertNotIn("test-secret", call.data.decode("utf-8"))
        self.assertEqual('{"ok":true}', response.content)
        self.assertEqual(12, response.usage.input_tokens)

    @patch("bsam_agent.openai_provider.urlopen")
    def test_maps_and_validates_responses_function_call(self, mocked: object) -> None:
        mocked.return_value = _Response({  # type: ignore[attr-defined]
            "status": "completed",
            "output": [{
                "type": "function_call", "call_id": "call-1",
                "name": "validate_model", "arguments": '{"source":"model.in"}',
            }],
        })
        response = OpenAIResponsesProvider(
            config(), credential_resolver=lambda _reference: "test-secret"
        ).complete(request(with_tools=True))
        self.assertEqual("validate_model", response.tool_calls[0].name)
        self.assertEqual({"source": "model.in"}, response.tool_calls[0].arguments)
        payload = json.loads(mocked.call_args.args[0].data)  # type: ignore[attr-defined]
        self.assertFalse(payload["tools"][0]["strict"])

    @patch("bsam_agent.openai_provider.urlopen")
    def test_invalid_function_arguments_are_rejected_locally(self, mocked: object) -> None:
        mocked.return_value = _Response({  # type: ignore[attr-defined]
            "status": "completed",
            "output": [{
                "type": "function_call", "call_id": "call-1",
                "name": "validate_model", "arguments": '{"source":42}',
            }],
        })
        with self.assertRaises(ProviderError) as raised:
            OpenAIResponsesProvider(
                config(), credential_resolver=lambda _reference: "test-secret"
            ).complete(request(with_tools=True))
        self.assertEqual("invalid_response", raised.exception.code)

    @patch("bsam_agent.openai_provider.urlopen")
    def test_function_call_uses_the_exact_offered_schema_before_dispatch(self, mocked: object) -> None:
        mocked.return_value = _Response({  # type: ignore[attr-defined]
            "status": "completed",
            "output": [{
                "type": "function_call", "call_id": "call-1",
                "name": "preview_parameter_change",
                "arguments": '{"source":"model.in","parameter":"d_reduction","value":"0.5"}',
            }],
        })
        offered = {
            "type": "object", "additionalProperties": False,
            "required": ["source", "parameter", "value"],
            "properties": {
                "source": {"type": "string"},
                "parameter": {"type": "string"},
                "value": {"type": "string"},
            },
        }
        routed = ProviderRequest(
            request().messages, {"preview_parameter_change": offered}, None,
            64, "hosted-relaxed", "sanitized",
        )
        response = OpenAIResponsesProvider(
            config(), credential_resolver=lambda _reference: "test-secret"
        ).complete(routed)
        self.assertEqual("preview_parameter_change", response.tool_calls[0].name)

    @patch("bsam_agent.openai_provider.urlopen")
    def test_missing_api_key_is_normalized_before_transport(self, mocked: object) -> None:
        with self.assertRaises(ProviderError) as raised:
            OpenAIResponsesProvider(
                config(), credential_resolver=lambda _reference: None
            ).complete(request())
        self.assertEqual("missing_api_key", raised.exception.code)
        mocked.assert_not_called()  # type: ignore[attr-defined]

    @patch("bsam_agent.openai_provider.urlopen")
    def test_private_policy_is_rejected_before_transport(self, mocked: object) -> None:
        private_request = ProviderRequest(
            request().messages, {}, None, 64, "hosted-2", "local-private"
        )
        with self.assertRaises(ProviderError) as raised:
            OpenAIResponsesProvider(
                config(), credential_resolver=lambda _reference: "test-secret"
            ).complete(private_request)
        self.assertEqual("data_policy_violation", raised.exception.code)
        mocked.assert_not_called()  # type: ignore[attr-defined]

    @patch("bsam_agent.openai_provider.urlopen")
    def test_preflight_cancellation_avoids_transport(self, mocked: object) -> None:
        cancel = threading.Event()
        cancel.set()
        with self.assertRaises(ProviderError) as raised:
            OpenAIResponsesProvider(config()).complete(request(), cancel)
        self.assertEqual("cancelled", raised.exception.code)
        mocked.assert_not_called()  # type: ignore[attr-defined]

    def test_factory_selects_openai_adapter(self) -> None:
        self.assertIsInstance(create_provider(config()), OpenAIResponsesProvider)

    @patch("bsam_agent.openai_provider.urlopen")
    def test_http_error_reports_only_bounded_code_and_parameter(self, mocked: object) -> None:
        body = json.dumps({
            "error": {
                "code": "invalid_json_schema",
                "param": "text.format.schema",
                "message": "sensitive vendor detail",
            }
        }).encode("utf-8")
        mocked.side_effect = HTTPError(  # type: ignore[attr-defined]
            "https://api.openai.com/v1/responses", 400, "Bad Request", {}, io.BytesIO(body)
        )
        with self.assertRaises(ProviderError) as raised:
            OpenAIResponsesProvider(
                config(), credential_resolver=lambda _reference: "test-secret"
            ).complete(request())
        message = str(raised.exception)
        self.assertIn("code=invalid_json_schema", message)
        self.assertIn("param=text.format.schema", message)
        self.assertNotIn("sensitive vendor detail", message)

    @patch("bsam_agent.openai_provider.urlopen")
    def test_synthetic_openai_to_orchestrator_to_deterministic_tool(self, mocked: object) -> None:
        mocked.return_value = _Response({  # type: ignore[attr-defined]
            "status": "completed",
            "output": [{
                "type": "function_call", "call_id": "call-1",
                "name": "validate_model", "arguments": '{"source":"model.in"}',
            }],
        })
        deck = (
            b"INPUT\n3\nEND INPUT\nBOUNDARY\n*type\nmechanical\nEND BOUNDARY\n"
            b"CONSTITUTIVE\n0\nEND CONSTITUTIVE\nMATERIALS\n0\nEND MATERIALS\n"
            b"CLUSTERS\n*type\nsolid\n*STOP\nEND CLUSTERS\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.in").write_bytes(deck)
            provider = OpenAIResponsesProvider(
                config(), credential_resolver=lambda _reference: "test-secret",
            )
            result = ChatOrchestrator(provider, config(), LocalAgentApi(root)).turn(
                "Assess synthetic model.in using the deterministic checks."
            )
        self.assertEqual("validate_model", result.tool)
        self.assertEqual(0, result.tool_result["summary"]["errors"])
        payload = json.loads(mocked.call_args.args[0].data)  # type: ignore[attr-defined]
        self.assertTrue(any(item["name"] == "validate_model" for item in payload["tools"]))


if __name__ == "__main__":
    unittest.main()
