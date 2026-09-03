"""OpenAI-compatible llama.cpp adapter with a strict loopback boundary."""

from __future__ import annotations

import ast
import json
import os
import queue
import re
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .provider import ProviderConfig, ProviderRequest, ProviderResponse, ToolCall, Usage
from .tool_contracts import TOOL_DESCRIPTIONS, validate_arguments


class ProviderError(RuntimeError):
    """Normalized provider failure that does not expose vendor response objects."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool,
        correlation_id: str,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.correlation_id = correlation_id


@dataclass(frozen=True)
class _WorkerResult:
    value: ProviderResponse | None = None
    error: ProviderError | None = None


def resolve_credential(reference: str | None) -> str | None:
    if reference is None:
        return None
    match = re.fullmatch(r"env:([A-Za-z_][A-Za-z0-9_]*)", reference)
    if not match:
        raise ValueError("credential_reference must use env:VARIABLE_NAME")
    value = os.environ.get(match.group(1))
    if not value:
        raise ValueError(f"credential environment variable is not set: {match.group(1)}")
    return value


class LlamaCppProvider:
    """Synchronous adapter for llama-server's loopback chat-completions API."""

    def __init__(
        self,
        config: ProviderConfig,
        credential_resolver: Callable[[str | None], str | None] = resolve_credential,
    ) -> None:
        if config.provider != "cpu-local":
            raise ValueError("llama.cpp adapter requires provider=cpu-local")
        self.config = config
        self._credential_resolver = credential_resolver

    def complete(
        self,
        request: ProviderRequest,
        cancel: threading.Event | None = None,
    ) -> ProviderResponse:
        if cancel is not None and cancel.is_set():
            raise self._error("cancelled", "provider request was cancelled", False, request)
        if sum(len(item.content) for item in request.messages) > self.config.max_input_characters:
            raise self._error(
                "request_too_large", "provider message context exceeds the configured limit",
                False, request,
            )

        results: queue.Queue[_WorkerResult] = queue.Queue(maxsize=1)

        def worker() -> None:
            try:
                results.put(_WorkerResult(value=self._send(request)))
            except ProviderError as exc:
                results.put(_WorkerResult(error=exc))
            except Exception as exc:  # defensive normalization at the transport boundary
                results.put(_WorkerResult(error=self._error(
                    "transport_error", f"local provider transport failed: {exc}", True, request
                )))

        thread = threading.Thread(
            target=worker,
            name=f"llama-provider-{request.correlation_id}",
            daemon=True,
        )
        thread.start()
        deadline = time.monotonic() + self.config.timeout_seconds
        while True:
            if cancel is not None and cancel.is_set():
                raise self._error("cancelled", "provider request was cancelled", False, request)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise self._error("timeout", "local provider request timed out", True, request)
            try:
                result = results.get(timeout=min(0.05, remaining))
            except queue.Empty:
                continue
            if result.error is not None:
                raise result.error
            assert result.value is not None
            return result.value

    def _send(self, provider_request: ProviderRequest) -> ProviderResponse:
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": [
                {"role": item.role, "content": item.content}
                for item in provider_request.messages
            ],
            "max_tokens": min(
                provider_request.max_output_tokens, self.config.max_output_tokens
            ),
            "temperature": 0,
        }
        if provider_request.tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": TOOL_DESCRIPTIONS.get(
                            name, f"BSAM Agent deterministic tool: {name}"
                        ),
                        "parameters": schema,
                    },
                }
                for name, schema in provider_request.tools.items()
            ]
            payload["tool_choice"] = "auto"
        if provider_request.response_schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "bsam_agent_response",
                    "strict": True,
                    "schema": provider_request.response_schema,
                },
            }

        headers = {"Content-Type": "application/json"}
        credential = self._credential_resolver(self.config.credential_reference)
        if credential:
            headers["Authorization"] = f"Bearer {credential}"
        raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        http_request = Request(
            self.config.endpoint.rstrip("/") + "/v1/chat/completions",
            data=raw,
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(http_request, timeout=self.config.timeout_seconds) as response:
                body = response.read()
        except HTTPError as exc:
            raise self._error(
                "http_error", f"local provider returned HTTP {exc.code}",
                exc.code == 429 or exc.code >= 500, provider_request,
            ) from exc
        except (TimeoutError, URLError, OSError) as exc:
            raise self._error(
                "transport_error", f"local provider is unavailable: {exc}",
                True, provider_request,
            ) from exc
        try:
            value = json.loads(body)
            return self._parse_response(value, provider_request)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise self._error(
                "invalid_response", f"local provider returned an invalid response: {exc}",
                False, provider_request,
            ) from exc

    def _parse_response(
        self,
        value: Any,
        provider_request: ProviderRequest,
    ) -> ProviderResponse:
        if not isinstance(value, dict) or not isinstance(value.get("choices"), list):
            raise ValueError("response must contain choices")
        if not value["choices"]:
            raise ValueError("response choices are empty")
        choice = value["choices"][0]
        message = choice["message"]
        if not isinstance(message, dict):
            raise ValueError("response message must be an object")
        content = message.get("content")
        if content is not None and not isinstance(content, str):
            raise ValueError("response content must be text or null")
        calls: list[ToolCall] = []
        for item in message.get("tool_calls") or []:
            function = item["function"]
            name = function["name"]
            if name not in provider_request.tools:
                raise ValueError(f"provider requested unknown tool: {name}")
            arguments = json.loads(function["arguments"])
            validate_arguments(name, arguments)
            calls.append(ToolCall(str(item["id"]), name, arguments))
        if not calls and content and re.match(r"^\s*\[[A-Za-z_][A-Za-z0-9_]*\s*\(", content):
            calls.extend(self._parse_native_calls(content, provider_request))
            content = None
        if content is None and not calls:
            raise ValueError("response contains neither content nor tool calls")
        usage_value = value.get("usage") or {}
        usage = Usage(
            int(usage_value.get("prompt_tokens", 0)),
            int(usage_value.get("completion_tokens", 0)),
        )
        return ProviderResponse(
            content=content,
            tool_calls=tuple(calls),
            usage=usage,
            finish_reason=str(choice.get("finish_reason", "stop")),
        )

    @staticmethod
    def _parse_native_calls(
        content: str,
        provider_request: ProviderRequest,
    ) -> tuple[ToolCall, ...]:
        """Parse Llama 4's documented ``[function(key=value)]`` form without executing it."""
        expression = ast.parse(content.strip(), mode="eval").body
        if not isinstance(expression, ast.List) or not expression.elts:
            raise ValueError("native tool response must be a non-empty list")
        calls: list[ToolCall] = []
        for index, node in enumerate(expression.elts):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                raise ValueError("native tool response contains a non-call value")
            if node.args or any(item.arg is None for item in node.keywords):
                raise ValueError("native tool calls require named arguments")
            name = node.func.id
            if name not in provider_request.tools:
                raise ValueError(f"provider requested unknown tool: {name}")
            arguments = {
                item.arg: LlamaCppProvider._literal(item.value) for item in node.keywords
            }
            validate_arguments(name, arguments)
            calls.append(ToolCall(
                f"{provider_request.correlation_id}-{index + 1}", name, arguments
            ))
        return tuple(calls)

    @staticmethod
    def _literal(node: ast.AST) -> Any:
        if isinstance(node, ast.Name) and node.id in {"true", "false", "null"}:
            return {"true": True, "false": False, "null": None}[node.id]
        return ast.literal_eval(node)

    @staticmethod
    def _error(
        code: str,
        message: str,
        retryable: bool,
        request: ProviderRequest,
    ) -> ProviderError:
        return ProviderError(
            code, message, retryable=retryable, correlation_id=request.correlation_id
        )
