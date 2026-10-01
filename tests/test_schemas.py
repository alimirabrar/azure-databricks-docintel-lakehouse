from datetime import date
from decimal import Decimal

from docintel.schemas import DocumentExtraction, consistency_issues, validate_payload


def _invoice(**overrides):
    base = {
        "doc_type": "invoice",
        "document_number": " INV-1 ",
        "vendor_name": "Contoso  Packaging Ltd",
        "issue_date": "2026-03-01",
        "due_date": "2026-03-31",
        "currency": "inr",
        "subtotal": "100.00",
        "tax": "18.00",
        "total": "118.00",
        "line_items": [
            {"description": "Box", "quantity": "2", "unit_price": "50.00", "amount": "100.00"}
        ],
    }
    base.update(overrides)
    return base


def test_valid_payload_is_coerced_and_cleaned():
    model, errors = validate_payload(_invoice())
    assert errors == []
    assert model is not None
    assert model.document_number == "INV-1"
    assert model.vendor_name == "Contoso Packaging Ltd"
    assert model.currency == "INR"
    assert model.issue_date == date(2026, 3, 1)
    assert model.total == Decimal("118.00")
    assert consistency_issues(model) == []


def test_invalid_doc_type_and_date_are_reported():
    model, errors = validate_payload(_invoice(doc_type="memo", issue_date="31/31/2026"))
    assert model is None
    assert any(e.startswith("doc_type") for e in errors)
    assert any(e.startswith("issue_date") for e in errors)


def test_negative_amount_rejected():
    model, errors = validate_payload(_invoice(total="-5"))
    assert model is None and any(e.startswith("total") for e in errors)


def test_consistency_issues_flag_bad_totals_and_dates():
    model = DocumentExtraction.model_validate(
        _invoice(total="200.00", due_date="2026-01-01", subtotal="90.00")
    )
    issues = consistency_issues(model)
    assert "subtotal_plus_tax_ne_total" in issues
    assert "line_items_sum_ne_subtotal" in issues
    assert "due_date_before_issue_date" in issues


def test_json_schema_is_exportable_for_structured_outputs():
    schema = DocumentExtraction.model_json_schema()
    assert "line_items" in schema["properties"]
    assert schema["required"] == ["doc_type"]
