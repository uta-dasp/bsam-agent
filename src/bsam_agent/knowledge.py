"""Non-authoritative retrieval boundary for future BSAM engineering knowledge."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


KNOWLEDGE_ACTIONS = (
    "search_bsam_knowledge",
    "retrieve_documentation",
    "find_similar_validated_examples",
    "search_troubleshooting_history",
)


@dataclass(frozen=True)
class KnowledgeQuery:
    action: str
    text: str
    capability: str | None = None
    limit: int = 5

    def __post_init__(self) -> None:
        if self.action not in KNOWLEDGE_ACTIONS:
            raise ValueError(f"unsupported knowledge action: {self.action}")
        if not self.text.strip():
            raise ValueError("knowledge query text cannot be empty")
        if self.limit < 1 or self.limit > 20:
            raise ValueError("knowledge query limit must be between 1 and 20")


@dataclass(frozen=True)
class KnowledgeEvidence:
    source_id: str
    title: str
    excerpt: str
    trust: str
    digest: str | None = None


class KnowledgeRetriever(Protocol):
    """Optional retrieval provider; returned evidence never grants BSAM authority."""

    def retrieve(self, query: KnowledgeQuery) -> tuple[KnowledgeEvidence, ...]: ...


class RetrievalUnavailable:
    """Fail-closed default used until a bounded knowledge index is configured."""

    def retrieve(self, query: KnowledgeQuery) -> tuple[KnowledgeEvidence, ...]:
        del query
        return ()
