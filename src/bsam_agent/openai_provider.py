"""OpenAI Responses API adapter with a fixed minimized-payload policy."""

from __future__ import annotations

import json
import queue
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .local_provider import ProviderError, resolve_credential
from .provider import ProviderConfig, ProviderRequest, ProviderResponse, ToolCall, Usage
from .tool_contracts import TOOL_DESCRIPTIONS, validate_arguments


@dataclass(frozen=True)
class _WorkerResult:
    value: ProviderResponse | None = None
    error: ProviderError | None = None


class OpenAIResponsesProvider:
    """Synchronous adapter for the official OpenAI Responses endpoint."""

    def __init__(
        self,
        config: ProviderConfig,
        credential_resolver: Callable[[str | None], str | None] = resolve_credential,
    ) -> None:
        if config.provider != "openai":
            raise ValueError("OpenAI adapter requires provider=openai")
        if config.store:
            raise ValueError("OpenAI adapter requires store=false")
        if config.data_policy not in {"synthetic-only", "sanitized"}:
            raise ValueError("OpenAI adapter does not accept local-private data")
        self.config = config
        self._credential_resolver = credential_resolver

    def complete(
        self,
        request: ProviderRequest,
        cancel: threading.Event | None = None,
    ) -> ProviderResponse:
        if request.data_policy not in {"synthetic-only", "sanitized"}:
            raise self._error(
                "data_policy_violation", "hosted provider rejected private payload", False, request
            )
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
            except Exception as exc:
                results.put(_WorkerResult(error=self._error(
                    "transport_error", f"OpenAI provider transport failed: {exc}", True, request
                )))

        thread = threading.Thread(
            target=worker,
            name=f"openai-provider-{request.correlation_id}",
            daemon=True,
        )
        thread.start()
        deadline = time.monotonic() + self.config.timeout_seconds
        while True:
            if cancel is not None and cancel.is_set():
                raise self._error("cancelled", "provider request was cancelled", False, request)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise self._error("timeout", "OpenAI provider request timed out", True, request)
            try:
                result = results.get(timeout=min(0.05, remaining))
            except queue.Empty:
                continue
            if result.error is not None:
                raise result.error
            assert result.value is not None
            return result.value

    def _send(self, provider_request: ProviderRequest) -> ProviderResponse:
        input_messages = [
            {"role": item.role, "content": item.content}
            for item in provider_request.messages
        ]
        if provider_request.response_schema is not None:
            schema_instruction = (
                "\nRequired response JSON Schema (use exactly these field names): "
                + json.dumps(
                    provider_request.response_schema,
                    separators=(",", ":"),
                    sort_keys=True,
                )
            )
            for message in input_messages:
                if message["role"] == "system":
                    message["content"] += schema_instruction
                    break
            else:
                input_messages.insert(0, {"role": "system", "content": schema_instruction.lstrip()})
        payload: dict[str, Any] = {
            "model": self.config.model,
            "input": input_messages,
            "max_output_tokens": min(
                provider_request.max_output_tokens, self.config.max_output_tokens
            ),
            "store": False,
        }
        if provider_request.tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "name": name,
                    "description": TOOL_DESCRIPTIONS.get(
                        name, f"BSAM Agent deterministic tool: {name}"
                    ),
                    "parameters": schema,
                    "strict": True,
                }
                for name, schema in provider_request.tools.items()
            ]
            payload["tool_choice"] = "auto"
        if provider_request.response_schema is not None:
            payload["text"] = {
                # The routing decision contains a tool-dependent arguments object. OpenAI's
                # strict schema mode requires every object property to be closed and required,
                # which cannot represent that provider-neutral union without changing it.
                # JSON mode guarantees parseable JSON; the orchestrator then applies the exact
                # decision schema included in the system message, tool allowlist, argument
                # schema, and one bounded repair.
                "format": {"type": "json_object"}
            }

        credential = self._credential_resolver(self.config.credential_reference)
        assert credential is not None
        raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        http_request = Request(
            self.config.endpoint.rstrip("/") + "/v1/responses",
            data=raw,
            headers={
                "Authorization": f"Bearer {credential}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(http_request, timeout=self.config.timeout_seconds) as response:
                body = response.read()
        except HTTPError as exc:
            detail = self._http_error_detail(exc)
            raise self._error(
                "http_error", f"OpenAI provider returned HTTP {exc.code}{detail}",
                exc.code == 429 or exc.code >= 500, provider_request,
            ) from exc
        except (TimeoutError, URLError, OSError) as exc:
            raise self._error(
                "transport_error", f"OpenAI provider is unavailable: {exc}",
                True, provider_request,
            ) from exc
        try:
            return self._parse_response(json.loads(body), provider_request)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise self._error(
                "invalid_response", f"OpenAI provider returned an invalid response: {exc}",
                False, provider_request,
            ) from exc

    def _parse_response(
        self,
        value: Any,
        provider_request: ProviderRequest,
    ) -> ProviderResponse:
        if not isinstance(value, dict) or not isinstance(value.get("output"), list):
            raise ValueError("response must contain output")
        text_parts: list[str] = []
        calls: list[ToolCall] = []
        for item in value["output"]:
            if not isinstance(item, dict):
                raise ValueError("response output item must be an object")
            if item.get("type") == "message":
                content = item.get("content")
                if not isinstance(content, list):
                    raise ValueError("response message content must be a list")
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "output_text":
                        if not isinstance(part.get("text"), str):
                            raise ValueError("response output text must be text")
                        text_parts.append(part["text"])
            elif item.get("type") == "function_call":
                name = item.get("name")
                if not isinstance(name, str) or name not in provider_request.tools:
                    raise ValueError(f"provider requested unknown tool: {name}")
                arguments = json.loads(item["arguments"])
                validate_arguments(name, arguments)
                call_id = item.get("call_id") or item.get("id")
                if not isinstance(call_id, str):
                    raise ValueError("function call has no identifier")
                calls.append(ToolCall(call_id, name, arguments))
        content = "\n".join(text_parts) or None
        if content is None and not calls:
            raise ValueError("response contains neither content nor tool calls")
        usage_value = value.get("usage") or {}
        usage = Usage(
            int(usage_value.get("input_tokens", 0)),
            int(usage_value.get("output_tokens", 0)),
        )
        status = str(value.get("status", "completed"))
        return ProviderResponse(content, tuple(calls), usage, status)

    @staticmethod
    def _http_error_detail(error: HTTPError) -> str:
        """Return bounded structural diagnostics without echoing request or response content."""
        try:
            value = json.loads(error.read(16384))
            detail = value.get("error") if isinstance(value, dict) else None
            if not isinstance(detail, dict):
                return ""
            code = detail.get("code")
            parameter = detail.get("param")
            parts = []
            if isinstance(code, str) and len(code) <= 80:
                parts.append(f"code={code}")
            if isinstance(parameter, str) and len(parameter) <= 160:
                parts.append(f"param={parameter}")
            return f" ({', '.join(parts)})" if parts else ""
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return ""

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
