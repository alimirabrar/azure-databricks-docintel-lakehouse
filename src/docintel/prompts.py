"""Versioned extraction prompts. The version is stored on every silver row and logged
to MLflow so accuracy can be compared across prompt revisions."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PromptTemplate:
    version: str
    system: str
    user: str

    def render(self, text: str) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": self.system},
            {"role": "user", "content": self.user.format(document=text)},
        ]


_V1_SYSTEM = (
    "You extract structured data from business documents (invoices, purchase orders, "
    "contracts). Return only JSON matching the provided schema. Use null for fields "
    "that are not present. Do not guess."
)

_V2_SYSTEM = (
    "You are a meticulous accounts-payable analyst. Extract structured fields from the "
    "document below and return ONLY JSON that matches the provided JSON schema.\n"
    "Rules:\n"
    "- doc_type is one of: invoice, purchase_order, contract.\n"
    "- Dates must be ISO-8601 (YYYY-MM-DD). Convert any other format.\n"
    "- Money values are plain decimals without currency symbols or thousands separators.\n"
    "- currency is an ISO-4217 code (e.g. INR, USD, EUR).\n"
    "- due_date = payment due date (invoice), delivery date (PO), end date (contract).\n"
    "- po_number is the purchase order referenced by an invoice; for a purchase order "
    "use document_number instead and leave po_number null.\n"
    "- For contracts, total is the total contract value.\n"
    "- The text may contain OCR errors (e.g. 0/O, 1/l); correct obvious ones.\n"
    "- Use null when a field is genuinely absent. Never invent values."
)

PROMPTS: dict[str, PromptTemplate] = {
    "v1": PromptTemplate("v1", _V1_SYSTEM, "Document:\n\n{document}"),
    "v2": PromptTemplate("v2", _V2_SYSTEM, "Document:\n<<<\n{document}\n>>>"),
}

DEFAULT_PROMPT_VERSION = "v2"


def get_prompt(version: str = DEFAULT_PROMPT_VERSION) -> PromptTemplate:
    try:
        return PROMPTS[version]
    except KeyError as exc:
        raise KeyError(f"Unknown prompt version {version!r}; known: {sorted(PROMPTS)}") from exc
