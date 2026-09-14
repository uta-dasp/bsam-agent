"""Construct the explicitly configured model-provider adapter."""

from __future__ import annotations

from .local_provider import LlamaCppProvider
from .openai_provider import OpenAIResponsesProvider
from .provider import Provider, ProviderConfig


def create_provider(config: ProviderConfig) -> Provider:
    if config.provider == "cpu-local":
        return LlamaCppProvider(config)
    if config.provider == "openai":
        return OpenAIResponsesProvider(config)
    raise ValueError(f"unsupported provider: {config.provider}")
