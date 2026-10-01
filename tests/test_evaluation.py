import pytest

from docintel.evaluation import evaluate, load_labels

LABEL = {
    "doc_type": "invoice",
    "document_number": "INV-1",
    "vendor_name": "Contoso Ltd",
    "buyer_name": None,
    "issue_date": "2026-01-01",
    "due_date": None,
    "po_number": None,
    "currency": "INR",
    "subtotal": "100.00",
    "tax": "18.00",
    "total": "118.00",
    "line_items": [
        {"description": "Box", "quantity": "2", "amount": "100.00", "unit_price": "50"},
    ],
}


def test_perfect_prediction():
    rep = evaluate({"d1": dict(LABEL)}, {"d1": LABEL})
    assert rep.micro.precision == rep.micro.recall == 1.0
    assert rep.line_items.f1 == 1.0
    assert rep.n_exact == 1


def test_wrong_value_costs_precision_and_recall():
    pred = dict(LABEL, total="999.00", vendor_name="contoso   LTD", buyer_name="Someone")
    rep = evaluate({"d1": pred}, {"d1": LABEL})
    total = rep.fields["total"]
    assert (total.tp, total.fp, total.fn) == (0, 1, 1)
    # case/whitespace-insensitive string match
    assert rep.fields["vendor_name"].tp == 1
    # hallucinated value where label is empty -> FP only
    buyer = rep.fields["buyer_name"]
    assert (buyer.tp, buyer.fp, buyer.fn) == (0, 1, 0)
    assert rep.n_exact == 0


def test_invalid_record_counts_as_all_missing():
    rep = evaluate({"d1": None}, {"d1": LABEL})
    assert rep.micro.tp == 0 and rep.micro.fp == 0
    assert rep.micro.fn == 8  # number of non-null scalar label fields
    assert rep.line_items.fn == 1
    assert rep.metrics()["schema_valid_rate"] == 0.0


def test_money_normalization_and_line_items():
    pred = dict(
        LABEL,
        total="118",
        line_items=[
            {"description": "box", "quantity": "2.0", "amount": "100"},
            {"description": "Extra", "quantity": "1", "amount": "5"},
        ],
    )
    rep = evaluate({"d1": pred}, {"d1": LABEL})
    assert rep.fields["total"].tp == 1
    li = rep.line_items
    assert (li.tp, li.fp, li.fn) == (1, 1, 0)
    assert li.precision == pytest.approx(0.5)


def test_markdown_and_sample_labels(sample_dir):
    labels = load_labels(sample_dir / "labels")
    assert len(labels) == 24
    md = evaluate({k: v for k, v in labels.items()}, labels).to_markdown()
    assert "| **micro_avg_scalar_fields** | 1.000 | 1.000 | 1.000 |" in md
