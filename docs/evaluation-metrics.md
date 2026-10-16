# Evaluation Metrics

This project compares predictions and labels keyed by `doc_id`. The evaluation code lives in `src/docintel/evaluation.py`; the local command writes a Markdown report and JSON metrics to `output/`.

## Scalar fields

The scalar score covers the 11 fields in `SCALAR_FIELDS`, including document type, identifiers, dates, currency, and totals. A normalized match is a true positive. A non-empty wrong or hallucinated value is a false positive; a missing labeled value is a false negative. A wrong non-empty value therefore counts as both a false positive and a false negative.

Text comparisons ignore case and repeated whitespace. Dates compare by their ISO date representation. Monetary values compare to two decimal places. Field-level precision, recall, and F1 are reported, along with micro scores aggregated across scalar fields.

## Line items

Line items are compared as a **multiset**, so row order does not affect the score and duplicate rows still count. Each match key includes normalized description, quantity, unit price, and amount. Monetary values are normalized to two decimal places; quantity keeps its full decimal precision.

The output reports line-item precision, recall, F1, and support. A mismatch in any line-item key also prevents that document from being counted as an exact match.

## Schema validity and exact documents

`schema_valid_rate` is the share of documents with a non-`None` prediction payload. In the pipeline, records that fail Pydantic validation are passed to the evaluator as `None` and are scored as empty predictions.

`doc_exact_match_rate` requires every normalized scalar field **and** the complete line-item multiset to match. The per-document error list includes `line_items` when its multiset differs. A record with correct header fields but a wrong item price, quantity, description, or amount is not exact.

## Reproduce the sample

Run the deterministic offline baseline without Azure credentials:

```bash
make install
make run
```

The current 24-document synthetic sample produces `doc_exact_match_rate = 0.625` (15/24) with the rule-based client. This is a reproducible baseline, not a production benchmark or an Azure OpenAI result. The sample is synthetic and small; use a larger representative labeled set before drawing conclusions about real documents.
