"""Provider-neutral types; model output is always untrusted structured input."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse


class ProviderConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Message:
    role: str
    content: str

    def __post_init__(self) -> None:
        if self.role not in {"system", "user", "assistant", "tool"}:
            raise ValueError(f"unsupported message role: {self.role}")


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True)
class ProviderRequest:
    messages: tuple[Message, ...]
    tools: dict[str, dict[str, Any]]
    response_schema: dict[str, Any] | None
    max_output_tokens: int
    correlation_id: str
    data_policy: str


@dataclass(frozen=True)
class ProviderResponse:
    content: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()
    usage: Usage = field(default_factory=Usage)
    finish_reason: str = "stop"


class Provider(Protocol):
    def complete(
        self,
        request: ProviderRequest,
        cancel: threading.Event | None = None,
    ) -> ProviderResponse: ...


@dataclass(frozen=True)
class ProviderConfig:
    provider: str
    model: str
    endpoint: str
    credential_reference: str | None
    timeout_seconds: float
    max_input_characters: int
    max_output_tokens: int
    data_policy: str


def load_provider_config(path: Path) -> ProviderConfig:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ProviderConfigError("provider configuration must be an object")
    allowed = {
        "provider", "model", "endpoint", "credential_reference", "timeout_seconds",
        "max_input_characters", "max_output_tokens", "data_policy",
    }
    extra = sorted(value.keys() - allowed)
    missing = sorted({"provider", "model", "endpoint"} - value.keys())
    if missing or extra:
        detail = []
        if missing:
            detail.append("missing: " + ", ".join(missing))
        if extra:
            detail.append("unknown: " + ", ".join(extra))
        raise ProviderConfigError("; ".join(detail))
    for forbidden in ("api_key", "token", "password", "secret"):
        if forbidden in value:
            raise ProviderConfigError("credentials must be referenced, never embedded")
    provider = str(value["provider"])
    endpoint = str(value["endpoint"])
    parsed = urlparse(endpoint)
    if provider == "cpu-local":
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ProviderConfigError("cpu-local provider endpoint must be loopback HTTP")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ProviderConfigError("cpu-local provider endpoint cannot embed credentials or options")
        if parsed.path not in {"", "/"}:
            raise ProviderConfigError("cpu-local provider endpoint must not include an API path")
    timeout = float(value.get("timeout_seconds", 120.0))
    max_input = int(value.get("max_input_characters", 24000))
    maximum = int(value.get("max_output_tokens", 2048))
    if timeout <= 0 or max_input <= 0 or maximum <= 0:
        raise ProviderConfigError("provider limits must be positive")
    policy = str(value.get("data_policy", "synthetic-only"))
    if policy not in {"local-private", "synthetic-only", "sanitized"}:
        raise ProviderConfigError("unsupported data policy")
    return ProviderConfig(
        provider, str(value["model"]), endpoint,
        str(value["credential_reference"]) if value.get("credential_reference") else None,
        timeout, max_input, maximum, policy,
    )
