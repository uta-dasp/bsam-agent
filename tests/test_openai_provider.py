from __future__ import annotations

import json
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bsam_agent.local_provider import ProviderError
from bsam_agent.openai_provider import OpenAIResponsesProvider
from bsam_agent.provider import Message, ProviderConfig, ProviderRequest
from bsam_agent.provider_factory import create_provider
from bsam_agent.tool_contracts import TOOL_CONTRACTS


def config() -> ProviderConfig:
    return ProviderConfig(
        "openai", "test-model", "https://api.openai.com", "env:OPENAI_API_KEY",
        2.0, 24000, 128, "sanitized", False,
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
    def test_uses_responses_api_store_false_and_structured_output(self, mocked: object) -> None:
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
        self.assertEqual("json_schema", payload["text"]["format"]["type"])
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


if __name__ == "__main__":
    unittest.main()
