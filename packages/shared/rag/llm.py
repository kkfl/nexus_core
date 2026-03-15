"""LLM provider for Ask Nexus answer synthesis.

Follows the same provider pattern as EmbeddingProvider.
Supports OpenAI-compatible APIs out of the box.
Set LLM_PROVIDER=disabled (or omit OPENAI_API_KEY) to fall back to
the V1 excerpt-concatenation behaviour — nothing breaks.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod

import structlog

logger = structlog.get_logger(__name__)

# ── System prompt for RAG answer synthesis ─────────────────────────────

_SYSTEM_PROMPT = """\
You are **Nexus Brain**, the AI assistant for the Nexus platform.
Your job is to answer the user's question using ONLY the context
documents provided below.

Rules:
1. Base your answer ONLY on the provided context. Do not hallucinate.
2. If the context does not contain enough information, say so clearly.
3. Cite your sources by referencing the document title in brackets,
   e.g. [Vultr API — Instances].
4. Use markdown formatting: headers, bullet points, code blocks as
   appropriate for developer-facing answers.
5. Keep your answer concise and actionable.

---

{context}
"""


# ── Abstract base ──────────────────────────────────────────────────────


class LLMProvider(ABC):
    @property
    @abstractmethod
    def model_name(self) -> str:
        pass

    @abstractmethod
    def complete(self, system_prompt: str, user_prompt: str) -> str:
        """Generate a completion given system + user prompts."""
        pass


# ── OpenAI implementation ──────────────────────────────────────────────


class OpenAILLMProvider(LLMProvider):
    def __init__(
        self,
        model: str | None = None,
        max_tokens: int | None = None,
    ) -> None:
        import openai

        self._model = model or os.environ.get("LLM_MODEL", "gpt-4o-mini")
        self._max_tokens = max_tokens or int(os.environ.get("LLM_MAX_TOKENS", "1024"))
        self._client = openai.OpenAI()  # reads OPENAI_API_KEY from env

    @property
    def model_name(self) -> str:
        return self._model

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=self._max_tokens,
            temperature=0.2,  # low temp for factual RAG answers
        )
        return response.choices[0].message.content or ""


# ── Factory ────────────────────────────────────────────────────────────


def get_llm_provider() -> LLMProvider | None:
    """Return the configured LLM provider, or None if disabled.

    Disabled when:
    - LLM_PROVIDER=disabled
    - LLM_PROVIDER=openai but OPENAI_API_KEY is missing
    """
    provider_type = os.environ.get("LLM_PROVIDER", "openai")

    if provider_type == "disabled":
        return None

    if provider_type == "openai":
        if not os.environ.get("OPENAI_API_KEY"):
            logger.warning("llm_provider_disabled", reason="OPENAI_API_KEY not set")
            return None
        return OpenAILLMProvider()

    logger.warning("llm_provider_unknown", provider=provider_type)
    return None


def build_rag_prompt(citations: list[dict]) -> str:
    """Build the system prompt with context from retrieved citations.

    Each citation dict should have 'title' and 'excerpt' keys.
    """
    if not citations:
        return _SYSTEM_PROMPT.replace("{context}", "(No relevant documents found.)")

    context_parts = []
    for i, c in enumerate(citations, 1):
        title = c.get("title", "Untitled")
        excerpt = c.get("excerpt", "")
        score = c.get("score", 0)
        context_parts.append(
            f"### Document {i}: {title} (relevance: {score:.0%})\n{excerpt}"
        )

    context_block = "\n\n---\n\n".join(context_parts)
    return _SYSTEM_PROMPT.replace("{context}", context_block)
