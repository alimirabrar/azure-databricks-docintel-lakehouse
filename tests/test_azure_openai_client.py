import json
from types import SimpleNamespace

import pytest

from docintel.extraction import extract_document
from docintel.llm.azure_openai import AzureOpenAIClient


class FakeCompletions:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        msg = SimpleNamespace(content=r)
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


def _client(responses):
    completions = FakeCompletions(responses)
    sdk = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return AzureOpenAIClient(deployment="gpt-4o-mini", sdk_client=sdk, max_retries=2), completions


def test_sends_schema_and_parses_json(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    payload = {"doc_type": "invoice", "vendor_name": "Contoso Packaging Ltd", "total": 10.5}
    client, completions = _client([json.dumps(payload)])
    res = extract_document("TAX INVOICE ...", client, "v2")
    assert res.is_valid and res.payload["vendor_name"] == "Contoso Packaging Ltd"
    assert res.model == "gpt-4o-mini" and res.client == "azure_openai"
    call = completions.calls[0]
    assert call["temperature"] == 0
    assert call["response_format"]["type"] == "json_schema"
    assert call["messages"][0]["role"] == "system"
    assert "TAX INVOICE" in call["messages"][1]["content"]


def test_retries_transient_errors(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    client, completions = _client([RuntimeError("429"), '{"doc_type": "contract"}'])
    assert client.extract("x", __import__("docintel.prompts").prompts.get_prompt()) == {
        "doc_type": "contract"
    }
    assert len(completions.calls) == 2


def test_gives_up_after_max_retries(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    client, _ = _client(["not json", "still not json"])
    from docintel.prompts import get_prompt

    with pytest.raises(RuntimeError, match="extraction failed"):
        client.extract("x", get_prompt())
