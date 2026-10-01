"""Pluggable LLM clients for structured extraction."""

from docintel.llm.base import LLMClient, get_client
from docintel.llm.rule_based import RuleBasedClient

__all__ = ["LLMClient", "RuleBasedClient", "get_client"]
