"""Azure OpenAI client using JSON-schema structured outputs."""

from __future__ import annotations

import json
import os
import time
from typing import Any

from docintel.prompts import PromptTemplate
from docintel.schemas import DocumentExtraction

DEFAULT_API_VERSION = "2024-10-21"


class AzureOpenAIClient:
    """Calls an Azure OpenAI chat deployment and returns the parsed JSON payload.

    Configuration (constructor args override environment variables):

    * ``AZURE_OPENAI_ENDPOINT`` - e.g. ``https://<name>.openai.azure.com``
    * ``AZURE_OPENAI_DEPLOYMENT`` - chat model deployment name (e.g. ``gpt-4o-mini``)
    * ``AZURE_OPENAI_API_KEY`` - optional; if unset, Microsoft Entra ID is used via
      ``azure-identity`` ``DefaultAzureCredential`` (managed identity on Databricks).
    * ``AZURE_OPENAI_API_VERSION`` - defaults to ``2024-10-21``.

    ``sdk_client`` lets tests (or callers with custom transport) inject a client
    exposing ``chat.completions.create``.
    """

    name = "azure_openai"

    def __init__(
        self,
        endpoint: str | None = None,
        deployment: str | None = None,
        api_key: str | None = None,
        api_version: str | None = None,
        max_retries: int = 3,
        sdk_client: Any | None = None,
    ) -> None:
        self.model = deployment or os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")
        self.max_retries = max_retries
        if sdk_client is not None:
            self._client = sdk_client
            return
        from openai import AzureOpenAI

        endpoint = endpoint or os.environ["AZURE_OPENAI_ENDPOINT"]
        api_version = api_version or os.environ.get("AZURE_OPENAI_API_VERSION", DEFAULT_API_VERSION)
        api_key = api_key or os.environ.get("AZURE_OPENAI_API_KEY")
        if api_key:
            self._client = AzureOpenAI(
                azure_endpoint=endpoint, api_key=api_key, api_version=api_version
            )
        else:  # pragma: no cover - requires Azure identity
            from azure.identity import DefaultAzureCredential, get_bearer_token_provider

            token_provider = get_bearer_token_provider(
                DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default"
            )
            self._client = AzureOpenAI(
                azure_endpoint=endpoint,
                azure_ad_token_provider=token_provider,
                api_version=api_version,
            )

    @staticmethod
    def response_format() -> dict[str, Any]:
        return {
            "type": "json_schema",
            "json_schema": {
                "name": "document_extraction",
                "schema": DocumentExtraction.model_json_schema(),
                # Non-strict: the Pydantic schema has optional fields/defaults; we
                # re-validate every payload with Pydantic anyway.
                "strict": False,
            },
        }

    def extract(self, text: str, prompt: PromptTemplate) -> dict[str, Any]:
        last_exc: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                resp = self._client.chat.completions.create(
                    model=self.model,
                    messages=prompt.render(text),
                    temperature=0,
                    response_format=self.response_format(),
                )
                content = resp.choices[0].message.content or "{}"
                return json.loads(content)
            except json.JSONDecodeError as exc:
                last_exc = exc
            except Exception as exc:  # transient API errors (429/5xx)
                last_exc = exc
                time.sleep(min(2**attempt, 8))
        raise RuntimeError(f"Azure OpenAI extraction failed: {last_exc}") from last_exc
