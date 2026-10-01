"""Pydantic schemas for structured document extraction.

A single, unified schema covers invoices, purchase orders and contracts so that the
silver layer can be one Delta table. Fields that do not apply to a document type are
left as ``None``.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

# Fields scored by the evaluation module (line items are scored separately).
SCALAR_FIELDS: tuple[str, ...] = (
    "doc_type",
    "document_number",
    "vendor_name",
    "buyer_name",
    "issue_date",
    "due_date",
    "po_number",
    "currency",
    "subtotal",
    "tax",
    "total",
)

MONEY_TOLERANCE = Decimal("0.02")


class DocType(str, Enum):
    INVOICE = "invoice"
    PURCHASE_ORDER = "purchase_order"
    CONTRACT = "contract"


class LineItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    description: str = Field(min_length=1)
    quantity: Decimal = Field(gt=0)
    unit_price: Decimal = Field(ge=0)
    amount: Decimal = Field(ge=0)

    @field_validator("description")
    @classmethod
    def _strip(cls, v: str) -> str:
        return " ".join(v.split())


class DocumentExtraction(BaseModel):
    """Structured fields extracted from a single business document."""

    model_config = ConfigDict(extra="ignore", use_enum_values=True)

    doc_type: DocType
    document_number: str | None = None
    vendor_name: str | None = None
    buyer_name: str | None = None
    issue_date: date | None = None
    due_date: date | None = Field(
        default=None,
        description="Payment due date (invoice), delivery date (PO) or end date (contract).",
    )
    po_number: str | None = Field(default=None, description="Referenced purchase order.")
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    subtotal: Decimal | None = Field(default=None, ge=0)
    tax: Decimal | None = Field(default=None, ge=0)
    total: Decimal | None = Field(default=None, ge=0)
    line_items: list[LineItem] = Field(default_factory=list)

    @field_validator("document_number", "vendor_name", "buyer_name", "po_number")
    @classmethod
    def _clean_str(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = " ".join(v.split())
        return v or None

    @field_validator("currency", mode="before")
    @classmethod
    def _upper_currency(cls, v: Any) -> Any:
        if isinstance(v, str):
            v = v.strip().upper()
            return v or None
        return v


def consistency_issues(doc: DocumentExtraction) -> list[str]:
    """Business-rule checks that do not invalidate a record but flag it for review."""
    issues: list[str] = []
    has_totals = doc.subtotal is not None and doc.tax is not None and doc.total is not None
    if has_totals and abs(doc.subtotal + doc.tax - doc.total) > MONEY_TOLERANCE:  # type: ignore[operator]
        issues.append("subtotal_plus_tax_ne_total")
    if doc.line_items and doc.subtotal is not None:
        items_sum = sum((li.amount for li in doc.line_items), Decimal("0"))
        if abs(items_sum - doc.subtotal) > MONEY_TOLERANCE:
            issues.append("line_items_sum_ne_subtotal")
    for i, li in enumerate(doc.line_items):
        if abs(li.quantity * li.unit_price - li.amount) > MONEY_TOLERANCE:
            issues.append(f"line_item_{i}_qty_x_price_ne_amount")
    if doc.issue_date and doc.due_date and doc.due_date < doc.issue_date:
        issues.append("due_date_before_issue_date")
    if doc.doc_type == DocType.INVOICE.value and doc.total is None:
        issues.append("invoice_missing_total")
    if doc.vendor_name is None:
        issues.append("missing_vendor")
    return issues


def validate_payload(payload: dict[str, Any]) -> tuple[DocumentExtraction | None, list[str]]:
    """Validate a raw LLM payload. Returns ``(model, errors)``; model is None on failure."""
    try:
        return DocumentExtraction.model_validate(payload), []
    except ValidationError as exc:
        errors = [
            f"{'.'.join(str(p) for p in err['loc']) or '<root>'}: {err['msg']}"
            for err in exc.errors()
        ]
        return None, errors
