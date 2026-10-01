from docintel.extraction import extract_document
from docintel.llm import RuleBasedClient, get_client
from docintel.llm.rule_based import parse_date, parse_money
from docintel.prompts import get_prompt

INVOICE = """TAX INVOICE
Contoso Packaging Ltd
Plot 14, Industrial Area Phase 2

Invoice No: INV-2026-0099
Invoice Date: 2026-02-10
Due Date: 2026-03-12
PO Reference: PO-12345

Bill To:
Example Manufacturing Co

Description | Qty | Unit Price | Amount
Steel bolts M8 | 100 | 12.50 | 1,250.00

Subtotal: INR 1,250.00
GST (18%): INR 225.00
Total Due: INR 1,475.00
"""


def test_extracts_invoice_fields():
    out = RuleBasedClient().extract(INVOICE, get_prompt("v2"))
    assert out["doc_type"] == "invoice"
    assert out["document_number"] == "INV-2026-0099"
    assert out["vendor_name"] == "Contoso Packaging Ltd"
    assert out["buyer_name"] == "Example Manufacturing Co"
    assert out["issue_date"] == "2026-02-10"
    assert out["due_date"] == "2026-03-12"
    assert out["po_number"] == "PO-12345"
    assert out["currency"] == "INR"
    assert (out["subtotal"], out["tax"], out["total"]) == ("1250.00", "225.00", "1475.00")
    assert out["line_items"] == [
        {
            "description": "Steel bolts M8",
            "quantity": "100",
            "unit_price": "12.50",
            "amount": "1250.00",
        }
    ]


def test_extract_document_validates_and_checks_consistency():
    res = extract_document(INVOICE, get_client("rule_based"), "v1")
    assert res.is_valid and res.errors == [] and res.issues == []
    assert res.prompt_version == "v1" and res.client == "rule_based"
    assert res.payload["total"] == "1475.00"


def test_unrecognised_document_goes_to_quarantine():
    res = extract_document("hello world", RuleBasedClient())
    assert not res.is_valid
    assert any(e.startswith("doc_type") for e in res.errors)


def test_client_error_is_captured():
    class Boom:
        name, model = "boom", "x"

        def extract(self, text, prompt):
            raise TimeoutError("upstream timeout")

    res = extract_document("TAX INVOICE", Boom())
    assert not res.is_valid and res.errors == ["client_error: upstream timeout"]


def test_parsers():
    assert parse_date("March 4, 2026").isoformat() == "2026-03-04"
    assert parse_date("04/03/2026").isoformat() == "2026-03-04"
    assert parse_date("1 February 2026").isoformat() == "2026-02-01"
    assert parse_date("not a date") is None
    assert str(parse_money("12,00,000.00")) == "1200000.00"
