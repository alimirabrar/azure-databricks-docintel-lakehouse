"""Field-level precision / recall / F1 of extracted records against labels.

Counting rules per field and document (standard for key-information extraction):

* label set, prediction equal            -> TP
* prediction set, label empty or differs -> FP
* label set, prediction empty or differs -> FN

A wrong value therefore costs both precision and recall. Line items are matched as
a multiset on (description, quantity, amount). Invalid records (failed schema
validation) count as empty predictions.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from docintel.schemas import SCALAR_FIELDS

_MONEY_FIELDS = {"subtotal", "tax", "total"}
_DATE_FIELDS = {"issue_date", "due_date"}


def _norm(fieldname: str, value: Any) -> Any:
    if value is None or value == "":
        return None
    if fieldname in _MONEY_FIELDS or fieldname in {"quantity", "amount", "unit_price"}:
        try:
            return Decimal(str(value).replace(",", "")).quantize(Decimal("0.01"))
        except InvalidOperation:
            return str(value)
    if fieldname in _DATE_FIELDS:
        return value.isoformat() if isinstance(value, date) else str(value)[:10]
    return " ".join(str(value).split()).casefold()


def _item_key(item: dict[str, Any]) -> tuple[Any, ...]:
    return (
        _norm("description", item.get("description")),
        _norm("quantity", item.get("quantity")),
        _norm("amount", item.get("amount")),
    )


@dataclass
class FieldScore:
    field: str
    tp: int = 0
    fp: int = 0
    fn: int = 0

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if (self.tp + self.fp) else 1.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if (self.tp + self.fn) else 1.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0

    @property
    def support(self) -> int:
        return self.tp + self.fn

    def as_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
            "tp": self.tp,
            "fp": self.fp,
            "fn": self.fn,
            "support": self.support,
        }


@dataclass
class EvalReport:
    fields: dict[str, FieldScore]
    line_items: FieldScore
    n_docs: int
    n_valid: int
    n_exact: int
    per_doc: list[dict[str, Any]] = field(default_factory=list)

    @property
    def micro(self) -> FieldScore:
        s = FieldScore("micro_avg_scalar_fields")
        for fs in self.fields.values():
            s.tp, s.fp, s.fn = s.tp + fs.tp, s.fp + fs.fp, s.fn + fs.fn
        return s

    def metrics(self) -> dict[str, float]:
        """Flat metric dict for MLflow."""
        m: dict[str, float] = {
            "micro_precision": self.micro.precision,
            "micro_recall": self.micro.recall,
            "micro_f1": self.micro.f1,
            "line_items_precision": self.line_items.precision,
            "line_items_recall": self.line_items.recall,
            "line_items_f1": self.line_items.f1,
            "schema_valid_rate": self.n_valid / self.n_docs if self.n_docs else 0.0,
            "doc_exact_match_rate": self.n_exact / self.n_docs if self.n_docs else 0.0,
            "n_docs": float(self.n_docs),
        }
        for name, fs in self.fields.items():
            m[f"{name}_precision"] = fs.precision
            m[f"{name}_recall"] = fs.recall
            m[f"{name}_f1"] = fs.f1
        return m

    def table(self) -> list[dict[str, Any]]:
        rows = [fs.as_dict() for fs in self.fields.values()]
        rows.append(self.line_items.as_dict())
        rows.append(self.micro.as_dict())
        return rows

    def to_markdown(self) -> str:
        out = ["| Field | Precision | Recall | F1 | Support |", "|---|---:|---:|---:|---:|"]
        for r in self.table():
            name = f"**{r['field']}**" if r["field"].startswith("micro") else f"`{r['field']}`"
            out.append(
                f"| {name} | {r['precision']:.3f} | {r['recall']:.3f} | {r['f1']:.3f} "
                f"| {r['support']} |"
            )
        return "\n".join(out)


def evaluate(
    predictions: dict[str, dict[str, Any] | None], labels: dict[str, dict[str, Any]]
) -> EvalReport:
    """Score ``predictions`` (doc_id -> payload or None) against ``labels``."""
    scores = {f: FieldScore(f) for f in SCALAR_FIELDS}
    items = FieldScore("line_items")
    n_valid = n_exact = 0
    per_doc = []
    for doc_id, label in sorted(labels.items()):
        pred = predictions.get(doc_id)
        if pred is not None:
            n_valid += 1
        pred = pred or {}
        wrong = []
        for f in SCALAR_FIELDS:
            lv, pv = _norm(f, label.get(f)), _norm(f, pred.get(f))
            if lv is not None and pv == lv:
                scores[f].tp += 1
                continue
            if pv is not None:
                scores[f].fp += 1
            if lv is not None:
                scores[f].fn += 1
            if pv != lv:
                wrong.append(f)
        lc = Counter(_item_key(i) for i in label.get("line_items") or [])
        pc = Counter(_item_key(i) for i in pred.get("line_items") or [])
        tp = sum((lc & pc).values())
        items.tp += tp
        items.fp += sum(pc.values()) - tp
        items.fn += sum(lc.values()) - tp
        if not wrong:
            n_exact += 1
        per_doc.append(
            {"doc_id": doc_id, "valid": bool(predictions.get(doc_id)), "wrong_fields": wrong}
        )
    return EvalReport(scores, items, len(labels), n_valid, n_exact, per_doc)


def load_labels(labels_dir: str | Path) -> dict[str, dict[str, Any]]:
    return {
        p.stem: json.loads(p.read_text(encoding="utf-8"))
        for p in sorted(Path(labels_dir).glob("*.json"))
    }
