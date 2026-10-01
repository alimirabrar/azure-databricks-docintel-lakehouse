"""Document -> validated structured record. Pure Python, used inside Spark UDFs."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

from docintel.llm.base import LLMClient
from docintel.prompts import DEFAULT_PROMPT_VERSION, get_prompt
from docintel.schemas import consistency_issues, validate_payload


@dataclass
class ExtractionResult:
    is_valid: bool
    payload: dict[str, Any] | None  # JSON-safe validated record (None if invalid)
    errors: list[str] = field(default_factory=list)  # schema validation errors
    issues: list[str] = field(default_factory=list)  # business-rule warnings
    prompt_version: str = DEFAULT_PROMPT_VERSION
    client: str = ""
    model: str = ""

    def to_json(self) -> str:
        return json.dumps(asdict(self))


def extract_document(
    text: str, client: LLMClient, prompt_version: str = DEFAULT_PROMPT_VERSION
) -> ExtractionResult:
    prompt = get_prompt(prompt_version)
    meta = {"prompt_version": prompt_version, "client": client.name, "model": client.model}
    try:
        raw = client.extract(text, prompt)
    except Exception as exc:  # keep the pipeline going; record lands in quarantine
        return ExtractionResult(False, None, [f"client_error: {exc}"], **meta)
    model, errors = validate_payload(raw)
    if model is None:
        return ExtractionResult(False, None, errors, **meta)
    return ExtractionResult(
        True, model.model_dump(mode="json"), [], consistency_issues(model), **meta
    )
