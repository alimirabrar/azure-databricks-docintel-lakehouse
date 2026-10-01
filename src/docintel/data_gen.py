"""Deterministic synthetic document generator.

Produces fictional invoices, purchase orders and contracts (no real companies or
personal data) in several layouts, plus ground-truth labels. A fraction of documents
get light OCR-style noise (e.g. ``0`` -> ``O``, ``I`` -> ``l``) so that extraction is
not trivially perfect.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

VENDORS = [
    "Deccan Industrial Supplies Pvt Ltd",
    "Northwind Components LLP",
    "Contoso Packaging Ltd",
    "Fabrikam Electricals Pvt Ltd",
    "Golconda Logistics Pvt Ltd",
    "Tailspin Office Solutions LLC",
]
BUYERS = [
    "Example Manufacturing Co",
    "Lakeview Retail Group Pvt Ltd",
    "Sample Foods Ltd",
]
ITEMS = [
    ("Steel bolts M8", Decimal("12.50")),
    ("Corrugated boxes 40x30", Decimal("38.00")),
    ("Copper cable 2.5mm (100m)", Decimal("2450.00")),
    ("Safety gloves (pair)", Decimal("95.00")),
    ("LED panel light 36W", Decimal("1180.00")),
    ("Pallet wrap film", Decimal("410.00")),
    ("Industrial adhesive 5L", Decimal("1725.00")),
    ("Printer toner cartridge", Decimal("3299.00")),
]
SERVICES = [
    "facility management services",
    "warehouse logistics services",
    "IT support and maintenance services",
]
MONTHS = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]

CENT = Decimal("0.01")


def _q(x: Decimal) -> Decimal:
    return x.quantize(CENT, rounding=ROUND_HALF_UP)


def _money(x: Decimal) -> str:
    return f"{x:,.2f}"


def _money_in(x: Decimal) -> str:
    """Indian digit grouping, e.g. 12,00,000.00."""
    whole, frac = f"{x:.2f}".split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups) + "," + tail
    return f"{whole}.{frac}"


def _long_date(d: date) -> str:
    return f"{MONTHS[d.month - 1]} {d.day}, {d.year}"


@dataclass
class SyntheticDoc:
    doc_id: str
    filename: str
    content: str
    label: dict[str, Any]


def _line_items(rng: random.Random, n: int) -> list[dict[str, Any]]:
    picks = rng.sample(ITEMS, n)
    items = []
    for desc, price in picks:
        qty = Decimal(rng.choice([1, 2, 4, 5, 10, 12, 20, 25, 50, 100]))
        items.append(
            {"description": desc, "quantity": qty, "unit_price": price, "amount": _q(qty * price)}
        )
    return items


def _jsonable(label: dict[str, Any]) -> dict[str, Any]:
    def conv(v: Any) -> Any:
        if isinstance(v, Decimal):
            return str(v)
        if isinstance(v, date):
            return v.isoformat()
        if isinstance(v, list):
            return [conv(x) for x in v]
        if isinstance(v, dict):
            return {k: conv(x) for k, x in v.items()}
        return v

    return conv(label)


def _invoice(
    rng: random.Random, idx: int, layout: int, known_pos: list[SyntheticDoc] | None = None
) -> SyntheticDoc:
    vendor, buyer = rng.choice(VENDORS), rng.choice(BUYERS)
    issue = date(2026, 1, 5) + timedelta(days=rng.randint(0, 200))
    due = issue + timedelta(days=rng.choice([15, 30, 45]))
    # About half of the invoices reference a PO that exists in the sample set, so the
    # gold layer has something to reconcile.
    if known_pos and rng.random() < 0.5:
        ref = rng.choice(known_pos).label
        po, vendor, buyer = ref["document_number"], ref["vendor_name"], ref["buyer_name"]
    else:
        po = f"PO-{rng.randint(10000, 99999)}"
    items = _line_items(rng, rng.randint(1, 4))
    subtotal = _q(sum((i["amount"] for i in items), Decimal("0")))
    currency, tax_rate = [
        ("INR", Decimal("0.18")),
        ("USD", Decimal("0.08")),
        ("EUR", Decimal("0.19")),
    ][layout]
    tax = _q(subtotal * tax_rate)
    total = subtotal + tax

    if layout == 0:
        number = f"INV-2026-{idx:04d}"
        rows = "\n".join(
            f"{i['description']} | {i['quantity']} | "
            f"{_money(i['unit_price'])} | {_money(i['amount'])}"
            for i in items
        )
        text = f"""TAX INVOICE
{vendor}
Plot 14, Industrial Area Phase 2

Invoice No: {number}
Invoice Date: {issue.isoformat()}
Due Date: {due.isoformat()}
PO Reference: {po}

Bill To:
{buyer}

Description | Qty | Unit Price | Amount
{rows}

Subtotal: INR {_money(subtotal)}
GST (18%): INR {_money(tax)}
Total Due: INR {_money(total)}
Amount in words: see total above.
"""
    elif layout == 1:
        number = f"{10000 + idx}"
        rows = "\n".join(
            f"{i['description']:<30}{int(i['quantity']):>5}   ${_money(i['unit_price']):>10}   "
            f"${_money(i['amount']):>10}"
            for i in items
        )
        text = f"""{vendor}
1200 Harbor Way, Suite 300
INVOICE

Invoice #: {number}
Date: {_long_date(issue)}
Payment Due: {_long_date(due)}
Customer: {buyer}
Your PO: {po}

ITEM                            QTY         RATE     LINE TOTAL
{rows}

Sub-total      ${_money(subtotal)}
Sales Tax      ${_money(tax)}
TOTAL          ${_money(total)} USD
Thank you for your business!
"""
    else:
        number = f"INV/26/{idx:04d}"
        rows = "\n".join(
            f"- {int(i['quantity'])} x {i['description']} @ EUR {_money(i['unit_price'])} "
            f"= EUR {_money(i['amount'])}"
            for i in items
        )
        text = f"""Invoice
Seller: {vendor}
Buyer: {buyer}
Invoice Number {number}
Issue date {issue.strftime("%d/%m/%Y")}
Due {due.strftime("%d/%m/%Y")}
Order ref. {po}

Items:
{rows}

Net amount: EUR {_money(subtotal)}
VAT 19%: EUR {_money(tax)}
Amount payable: EUR {_money(total)}
"""
    label = {
        "doc_type": "invoice",
        "document_number": number,
        "vendor_name": vendor,
        "buyer_name": buyer,
        "issue_date": issue,
        "due_date": due,
        "po_number": po,
        "currency": currency,
        "subtotal": subtotal,
        "tax": tax,
        "total": total,
        "line_items": items,
    }
    doc_id = f"inv_{idx:03d}"
    return SyntheticDoc(doc_id, f"{doc_id}.txt", text, _jsonable(label))


def _purchase_order(rng: random.Random, idx: int) -> SyntheticDoc:
    vendor, buyer = rng.choice(VENDORS), rng.choice(BUYERS)
    issue = date(2026, 1, 5) + timedelta(days=rng.randint(0, 200))
    delivery = issue + timedelta(days=rng.choice([7, 14, 21]))
    number = f"PO-{rng.randint(10000, 99999)}"
    items = _line_items(rng, rng.randint(2, 4))
    subtotal = _q(sum((i["amount"] for i in items), Decimal("0")))
    tax = _q(subtotal * Decimal("0.18"))
    total = subtotal + tax
    rows = "\n".join(
        f"{n}. {i['description']} | {i['quantity']} | "
        f"{_money(i['unit_price'])} | {_money(i['amount'])}"
        for n, i in enumerate(items, 1)
    )
    text = f"""PURCHASE ORDER
PO Number: {number}
Order Date: {issue.isoformat()}
Deliver By: {delivery.isoformat()}
Buyer: {buyer}
Supplier: {vendor}
Currency: INR

# Item | Qty | Unit Price | Amount
{rows}

Subtotal: {_money(subtotal)}
Tax (18%): {_money(tax)}
Order Total: {_money(total)}
Authorised signatory: Procurement Desk
"""
    label = {
        "doc_type": "purchase_order",
        "document_number": number,
        "vendor_name": vendor,
        "buyer_name": buyer,
        "issue_date": issue,
        "due_date": delivery,
        "po_number": None,
        "currency": "INR",
        "subtotal": subtotal,
        "tax": tax,
        "total": total,
        "line_items": items,
    }
    doc_id = f"po_{idx:03d}"
    return SyntheticDoc(doc_id, f"{doc_id}.txt", text, _jsonable(label))


def _contract(rng: random.Random, idx: int) -> SyntheticDoc:
    vendor, buyer = rng.choice(VENDORS), rng.choice(BUYERS)
    start = date(2026, rng.randint(1, 9), 1)
    end = date(start.year + 1, start.month, 1) - timedelta(days=1)
    value = Decimal(rng.choice([480000, 750000, 1200000, 2400000]))
    number = f"MSA-2026-{idx:03d}"
    service = rng.choice(SERVICES)
    page1 = [
        "MASTER SERVICES AGREEMENT",
        f"Agreement No.: {number}",
        f"This Agreement is entered into on {start.day} {MONTHS[start.month - 1]} {start.year}",
        f'between {buyer} ("Client") and {vendor} ("Service Provider")',
        f"for the provision of {service}.",
    ]
    page2 = [
        "Term: This Agreement remains in force until "
        f"{end.day} {MONTHS[end.month - 1]} {end.year}.",
        f"Total Contract Value: INR {_money_in(value)}",
        "Payment Terms: monthly in arrears, net 30 days.",
        "Governing law: as agreed between the parties.",
    ]
    ocr = {
        "source": "synthetic-ocr",
        "pages": [{"page": 1, "lines": page1}, {"page": 2, "lines": page2}],
    }
    label = {
        "doc_type": "contract",
        "document_number": number,
        "vendor_name": vendor,
        "buyer_name": buyer,
        "issue_date": start,
        "due_date": end,
        "po_number": None,
        "currency": "INR",
        "subtotal": None,
        "tax": None,
        "total": _q(value),
        "line_items": [],
    }
    doc_id = f"ctr_{idx:03d}"
    return SyntheticDoc(doc_id, f"{doc_id}.json", json.dumps(ocr, indent=2), _jsonable(label))


_NOISE = [("0", "O"), ("1", "l"), ("I", "l"), ("o", "0"), (":", ";"), ("5", "S")]


def _add_ocr_noise(text: str, rng: random.Random, n_edits: int) -> str:
    chars = list(text)
    for _ in range(n_edits):
        src, dst = rng.choice(_NOISE)
        positions = [i for i, c in enumerate(chars) if c == src]
        if positions:
            chars[rng.choice(positions)] = dst
    return "".join(chars)


def generate(
    n_invoices: int = 12,
    n_pos: int = 6,
    n_contracts: int = 6,
    seed: int = 42,
    noise_rate: float = 0.35,
) -> list[SyntheticDoc]:
    rng = random.Random(seed)
    pos = [_purchase_order(rng, i + 1) for i in range(n_pos)]
    docs = [_invoice(rng, i + 1, i % 3, pos) for i in range(n_invoices)]
    docs += pos
    docs += [_contract(rng, i + 1) for i in range(n_contracts)]
    for d in docs:
        if rng.random() < noise_rate:
            if d.filename.endswith(".json"):
                ocr = json.loads(d.content)
                for page in ocr["pages"]:
                    page["lines"] = [_add_ocr_noise(ln, rng, 1) for ln in page["lines"]]
                d.content = json.dumps(ocr, indent=2)
            else:
                d.content = _add_ocr_noise(d.content, rng, rng.randint(2, 4))
    return docs


def write_sample(out_dir: str | Path, **kwargs: Any) -> list[SyntheticDoc]:
    out = Path(out_dir)
    (out / "raw").mkdir(parents=True, exist_ok=True)
    (out / "labels").mkdir(parents=True, exist_ok=True)
    docs = generate(**kwargs)
    for d in docs:
        (out / "raw" / d.filename).write_text(d.content, encoding="utf-8")
        (out / "labels" / f"{d.doc_id}.json").write_text(
            json.dumps(d.label, indent=2) + "\n", encoding="utf-8"
        )
    return docs
