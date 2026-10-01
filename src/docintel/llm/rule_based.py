"""Deterministic, regex/heuristic extractor that mimics an LLM client.

It lets the whole pipeline (Spark jobs, validation, evaluation, MLflow) run locally
and in CI with no credentials, and gives a reproducible baseline to compare LLM
prompt versions against. It ignores the prompt and does *not* correct OCR errors,
so it is intentionally weaker than a good LLM on noisy text.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from docintel.prompts import PromptTemplate

_COMPANY_SUFFIX = re.compile(r"\b(Pvt Ltd|LLP|Ltd|LLC|Inc\.?|GmbH|Co\.?|Corporation)$")
_MONEY = r"(?:[$€₹]|INR|USD|EUR)?\s*([0-9][0-9,]*\.[0-9]{2})"
_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%B %d, %Y", "%d %B %Y", "%d-%m-%Y", "%b %d, %Y")

_LABELS: dict[str, list[str]] = {
    "document_number": [
        r"^(?:Invoice|PO|Agreement)\s*(?:No\.?|Number|#)\s*[:.]?\s*([A-Z0-9][A-Z0-9/\-]*)",
    ],
    "issue_date": [
        r"^(?:Invoice Date|Issue date|Order Date|Date)\s*[:]?\s*(.+)$",
        r"entered into on\s+(\d{1,2} [A-Z][a-z]+ \d{4})",
    ],
    "due_date": [
        r"^(?:Due Date|Payment Due|Due|Deliver By)\s*[:]?\s*(.+)$",
        r"in force until\s+(\d{1,2} [A-Z][a-z]+ \d{4})",
    ],
    "po_number": [r"^(?:PO Reference|Your PO|Order ref\.?)\s*[:]?\s*(PO-\d+)"],
    "vendor_name": [
        r"^(?:Seller|Supplier|Vendor)\s*:\s*(.+)$",
        r'and (.+?) \("Service Provider"\)',
    ],
    "buyer_name": [
        r"^(?:Buyer|Customer|Bill To)\s*:\s*(.+)$",
        r'between (.+?) \("Client"\)',
    ],
    "subtotal": [rf"^(?:Subtotal|Sub-total|Net amount)\s*:?\s*{_MONEY}"],
    "tax": [rf"^(?:GST|Tax|Sales Tax|VAT)\b[^:$€₹0-9]*(?:\([^)]*\))?\s*(?:\d+%)?\s*:?\s*{_MONEY}"],
    "total": [
        rf"^(?:Total Due|TOTAL|Amount payable|Order Total|Grand Total|Total Contract Value)"
        rf"\s*:?\s*{_MONEY}",
    ],
}

_ROW_PIPE = re.compile(
    r"^(?:\d+\.\s*)?(?P<desc>[^|]+?)\s*\|\s*(?P<qty>\d+(?:\.\d+)?)\s*\|\s*"
    r"(?P<price>[0-9][0-9,]*\.\d{2})\s*\|\s*(?P<amount>[0-9][0-9,]*\.\d{2})\s*$"
)
_ROW_SPACED = re.compile(
    r"^(?P<desc>\S.*?\S)\s{2,}(?P<qty>\d+)\s+\$\s*(?P<price>[0-9][0-9,]*\.\d{2})"
    r"\s+\$\s*(?P<amount>[0-9][0-9,]*\.\d{2})\s*$"
)
_ROW_AT = re.compile(
    r"^-\s*(?P<qty>\d+)\s*x\s*(?P<desc>.+?)\s*@\s*(?:[A-Z]{3}|[$€₹])\s*"
    r"(?P<price>[0-9][0-9,]*\.\d{2})\s*=\s*(?:[A-Z]{3}|[$€₹])\s*(?P<amount>[0-9][0-9,]*\.\d{2})\s*$"
)


def parse_date(raw: str) -> date | None:
    raw = raw.strip().rstrip(".")
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def parse_money(raw: str) -> Decimal | None:
    try:
        return Decimal(raw.replace(",", ""))
    except InvalidOperation:
        return None


class RuleBasedClient:
    name = "rule_based"
    model = "rules-v1"

    def extract(self, text: str, prompt: PromptTemplate | None = None) -> dict[str, Any]:
        lines = [ln.strip() for ln in text.split("\n")]
        out: dict[str, Any] = {"doc_type": self._doc_type(text)}

        for field, patterns in _LABELS.items():
            out[field] = self._first_match(lines, text, patterns)

        for f in ("issue_date", "due_date"):
            d = parse_date(out[f]) if out[f] else None
            out[f] = d.isoformat() if d else None
        for f in ("subtotal", "tax", "total"):
            m = parse_money(out[f]) if out[f] else None
            out[f] = str(m) if m is not None else None

        if out["vendor_name"] is None:
            out["vendor_name"] = self._header_company(lines, exclude=out.get("buyer_name"))
        if out["buyer_name"] is None:
            out["buyer_name"] = self._line_after(lines, r"^Bill To\s*:?\s*$")
        if out["doc_type"] == "purchase_order":
            out["po_number"] = None
        out["currency"] = self._currency(text)
        out["line_items"] = self._line_items(lines)
        return out

    @staticmethod
    def _doc_type(text: str) -> str | None:
        head = text[:400].upper()
        if "AGREEMENT" in head or "CONTRACT" in head:
            return "contract"
        if "PURCHASE ORDER" in head:
            return "purchase_order"
        if "INVOICE" in head:
            return "invoice"
        return None

    @staticmethod
    def _first_match(lines: list[str], text: str, patterns: list[str]) -> str | None:
        for pat in patterns:
            rx = re.compile(pat, re.MULTILINE)
            target = text if not pat.startswith("^") else None
            if target is not None:
                m = rx.search(" ".join(text.split()))
                if m:
                    return m.group(1).strip()
                continue
            for ln in lines:
                m = rx.search(ln)
                if m:
                    return m.group(1).strip()
        return None

    @staticmethod
    def _header_company(lines: list[str], exclude: str | None) -> str | None:
        for ln in lines[:6]:
            if ln and _COMPANY_SUFFIX.search(ln) and ln != exclude and ":" not in ln:
                return ln
        return None

    @staticmethod
    def _line_after(lines: list[str], pattern: str) -> str | None:
        rx = re.compile(pattern, re.IGNORECASE)
        for i, ln in enumerate(lines):
            if rx.match(ln):
                for nxt in lines[i + 1 :]:
                    if nxt:
                        return nxt
        return None

    @staticmethod
    def _currency(text: str) -> str | None:
        m = re.search(r"\b(INR|USD|EUR|GBP)\b", text)
        if m:
            return m.group(1)
        for sym, code in (("$", "USD"), ("€", "EUR"), ("₹", "INR")):
            if sym in text:
                return code
        return None

    @staticmethod
    def _line_items(lines: list[str]) -> list[dict[str, str]]:
        items = []
        for ln in lines:
            for rx in (_ROW_PIPE, _ROW_AT, _ROW_SPACED):
                m = rx.match(ln)
                if m:
                    items.append(
                        {
                            "description": m.group("desc").strip(),
                            "quantity": m.group("qty"),
                            "unit_price": m.group("price").replace(",", ""),
                            "amount": m.group("amount").replace(",", ""),
                        }
                    )
                    break
        return items
