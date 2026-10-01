"""Turn raw document bytes into plain text (the "OCR" step between bronze and silver).

Supported locally, without any cloud dependency:

* ``.txt`` / ``.md``: UTF-8 text (e.g. emails, e-invoices, pre-OCR'd text)
* ``.json``: OCR output in a simple page/line layout, the same shape we persist when
  documents are OCR'd upstream: ``{"pages": [{"page": 1, "lines": ["...", ...]}]}``
* ``.pdf``: digital PDFs via ``pypdf`` (optional extra ``[pdf]``)

Scanned images / PDFs are handled by :class:`AzureDocumentIntelligenceOCR`, which wraps
the Azure AI Document Intelligence ``prebuilt-read`` model (optional extra ``[azure]``).
"""

from __future__ import annotations

import io
import json
import os
import re
import unicodedata


class UnsupportedDocumentError(ValueError):
    pass


def normalize_text(text: str) -> str:
    """Normalize unicode, line endings and runs of blank lines."""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _ocr_json_to_text(content: bytes) -> str:
    data = json.loads(content.decode("utf-8"))
    pages = data.get("pages") if isinstance(data, dict) else None
    if not isinstance(pages, list):
        raise UnsupportedDocumentError("OCR JSON must contain a 'pages' list")
    out: list[str] = []
    for page in sorted(pages, key=lambda p: p.get("page", 0)):
        out.extend(str(line) for line in page.get("lines", []))
        out.append("")
    return "\n".join(out)


def _pdf_to_text(content: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise UnsupportedDocumentError("Install the [pdf] extra to read PDFs") from exc
    reader = PdfReader(io.BytesIO(content))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def extract_text(content: bytes, path: str) -> str:
    """Extract normalized text from document bytes based on the file extension."""
    ext = os.path.splitext(path.lower())[1]
    if ext in {".txt", ".md", ".eml"}:
        raw = content.decode("utf-8", errors="replace")
    elif ext == ".json":
        raw = _ocr_json_to_text(content)
    elif ext == ".pdf":
        raw = _pdf_to_text(content)
    else:
        raise UnsupportedDocumentError(f"Unsupported document type: {ext or path}")
    return normalize_text(raw)


class AzureDocumentIntelligenceOCR:  # pragma: no cover - requires Azure credentials
    """OCR for scanned PDFs/images using Azure AI Document Intelligence ``prebuilt-read``.

    Requires ``pip install 'azure-databricks-docintel-lakehouse[azure]'`` and
    ``AZURE_DOCINTEL_ENDPOINT`` (+ ``AZURE_DOCINTEL_KEY`` or a managed identity).
    """

    def __init__(self, endpoint: str | None = None, key: str | None = None) -> None:
        from azure.ai.documentintelligence import DocumentIntelligenceClient
        from azure.core.credentials import AzureKeyCredential

        endpoint = endpoint or os.environ["AZURE_DOCINTEL_ENDPOINT"]
        key = key or os.environ.get("AZURE_DOCINTEL_KEY")
        if key:
            credential = AzureKeyCredential(key)
        else:
            from azure.identity import DefaultAzureCredential

            credential = DefaultAzureCredential()
        self._client = DocumentIntelligenceClient(endpoint=endpoint, credential=credential)

    def __call__(self, content: bytes) -> str:
        poller = self._client.begin_analyze_document("prebuilt-read", body=content)
        result = poller.result()
        return normalize_text(result.content or "")
