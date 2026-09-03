from __future__ import annotations

import json
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bsam_agent.local_provider import LlamaCppProvider, ProviderError
from bsam_agent.provider import Message, ProviderConfig, ProviderRequest
from bsam_agent.tool_contracts import TOOL_CONTRACTS


def config() -> ProviderConfig:
    return ProviderConfig(
        "cpu-local", "test-model", "http://127.0.0.1:18080", None,
        2.0, 24000, 128, "synthetic-only",
    )


def request() -> ProviderRequest:
    return ProviderRequest(
        messages=(Message("user", "Validate model.in"),),
        tools={"validate_model": TOOL_CONTRACTS["validate_model"].request_schema()},
        response_schema=None,
        max_output_tokens=64,
        correlation_id="test-1",
        data_policy="synthetic-only",
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


class LocalProviderTests(unittest.TestCase):
    @patch("bsam_agent.local_provider.urlopen")
    def test_maps_and_validates_tool_call(self, mocked: object) -> None:
        mocked.return_value = _Response({  # type: ignore[attr-defined]
            "choices": [{
                "message": {
                    "content": None,
                    "tool_calls": [{
                        "id": "call-1", "type": "function",
                        "function": {"name": "validate_model", "arguments": "{\"source\":\"model.in\"}"},
                    }],
                },
                "finish_reason": "tool_calls",
            }],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        })
        response = LlamaCppProvider(config()).complete(request())
        self.assertEqual("validate_model", response.tool_calls[0].name)
        self.assertEqual({"source": "model.in"}, response.tool_calls[0].arguments)
        self.assertEqual(10, response.usage.input_tokens)

    @patch("bsam_agent.local_provider.urlopen")
    def test_rejects_invalid_tool_arguments(self, mocked: object) -> None:
        mocked.return_value = _Response({  # type: ignore[attr-defined]
            "choices": [{
                "message": {
                    "content": None,
                    "tool_calls": [{
                        "id": "call-1", "type": "function",
                        "function": {"name": "validate_model", "arguments": "{}"},
                    }],
                },
            }],
        })
        with self.assertRaises(ProviderError) as raised:
            LlamaCppProvider(config()).complete(request())
        self.assertEqual("invalid_response", raised.exception.code)
        self.assertFalse(raised.exception.retryable)

    @patch("bsam_agent.local_provider.urlopen")
    def test_preflight_cancellation_avoids_transport(self, mocked: object) -> None:
        cancel = threading.Event()
        cancel.set()
        with self.assertRaises(ProviderError) as raised:
            LlamaCppProvider(config()).complete(request(), cancel)
        self.assertEqual("cancelled", raised.exception.code)
        mocked.assert_not_called()  # type: ignore[attr-defined]

    @patch("bsam_agent.local_provider.urlopen")
    def test_context_limit_avoids_transport(self, mocked: object) -> None:
        limited = ProviderConfig(
            "cpu-local", "test-model", "http://127.0.0.1:18080", None,
            2.0, 4, 128, "synthetic-only",
        )
        with self.assertRaises(ProviderError) as raised:
            LlamaCppProvider(limited).complete(request())
        self.assertEqual("request_too_large", raised.exception.code)
        mocked.assert_not_called()  # type: ignore[attr-defined]

    @patch("bsam_agent.local_provider.urlopen")
    def test_parses_llama4_native_tool_syntax_without_execution(self, mocked: object) -> None:
        mocked.return_value = _Response({  # type: ignore[attr-defined]
            "choices": [{
                "message": {"content": '[validate_model(source="model.in")]'},
                "finish_reason": "stop",
            }],
        })
        response = LlamaCppProvider(config()).complete(request())
        self.assertIsNone(response.content)
        self.assertEqual("validate_model", response.tool_calls[0].name)
        self.assertEqual({"source": "model.in"}, response.tool_calls[0].arguments)

    @patch("bsam_agent.local_provider.urlopen")
    def test_native_tool_parser_rejects_expressions(self, mocked: object) -> None:
        mocked.return_value = _Response({  # type: ignore[attr-defined]
            "choices": [{
                "message": {"content": '[validate_model(source=danger())]'},
            }],
        })
        with self.assertRaises(ProviderError) as raised:
            LlamaCppProvider(config()).complete(request())
        self.assertEqual("invalid_response", raised.exception.code)


if __name__ == "__main__":
    unittest.main()
