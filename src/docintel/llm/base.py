from __future__ import annotations

import os
from typing import Any, Protocol, runtime_checkable

from docintel.prompts import PromptTemplate


@runtime_checkable
class LLMClient(Protocol):
    """Anything that turns document text + a prompt into a JSON-like payload."""

    name: str
    model: str

    def extract(self, text: str, prompt: PromptTemplate) -> dict[str, Any]: ...


def get_client(kind: str | None = None, **kwargs: Any) -> LLMClient:
    """Build a client by name: ``rule_based`` (default, offline) or ``azure_openai``.

    The default can be set with the ``DOCINTEL_LLM_CLIENT`` environment variable.
    """
    kind = (kind or os.environ.get("DOCINTEL_LLM_CLIENT") or "rule_based").lower()
    if kind in {"rule_based", "mock", "rules"}:
        from docintel.llm.rule_based import RuleBasedClient

        return RuleBasedClient()
    if kind in {"azure_openai", "azure", "aoai"}:
        from docintel.llm.azure_openai import AzureOpenAIClient

        return AzureOpenAIClient(**kwargs)
    raise ValueError(f"Unknown LLM client {kind!r}")
