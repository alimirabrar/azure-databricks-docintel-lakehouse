"""End-to-end local run: bronze -> silver -> gold -> evaluation -> MLflow."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pyspark.sql import DataFrame, SparkSession

from docintel.evaluation import EvalReport, evaluate, load_labels
from docintel.pipeline import bronze, gold, silver
from docintel.pipeline.io import TableTarget
from docintel.prompts import DEFAULT_PROMPT_VERSION
from docintel.schemas import SCALAR_FIELDS


def silver_to_predictions(silver_df: DataFrame) -> dict[str, dict[str, Any] | None]:
    """Collect silver rows into ``doc_id -> payload`` (None for invalid records)."""
    cols = ["doc_id", "is_valid", *SCALAR_FIELDS, "line_items"]
    preds: dict[str, dict[str, Any] | None] = {}
    for row in silver_df.select(*cols).collect():
        d = row.asDict(recursive=True)
        doc_id = d.pop("doc_id")
        preds[doc_id] = d if d.pop("is_valid") else None
    return preds


@dataclass
class RunResult:
    tables: dict[str, str]
    report: EvalReport
    run_id: str | None


def run_pipeline(
    spark: SparkSession,
    raw_path: str,
    target: TableTarget,
    *,
    client_kind: str = "rule_based",
    prompt_version: str = DEFAULT_PROMPT_VERSION,
    labels_dir: str | None = None,
    track: bool = False,
    experiment: str | None = None,
) -> RunResult:
    tables: dict[str, str] = {}
    b = bronze.dedupe_bronze(bronze.to_bronze(bronze.read_raw_documents(spark, raw_path)))
    tables["bronze_documents"] = target.write(b, "bronze_documents")
    b = target.read(spark, "bronze_documents")

    s = silver.to_silver(b, client_kind=client_kind, prompt_version=prompt_version)
    tables["silver_documents"] = target.write(s, "silver_documents")
    s = target.read(spark, "silver_documents")
    tables["silver_line_items"] = target.write(silver.to_line_items(s), "silver_line_items")

    tables["gold_vendor_spend"] = target.write(gold.vendor_spend(s), "gold_vendor_spend")
    tables["gold_extraction_quality"] = target.write(
        gold.extraction_quality(s), "gold_extraction_quality"
    )
    tables["gold_po_invoice_reconciliation"] = target.write(
        gold.po_invoice_reconciliation(s), "gold_po_invoice_reconciliation"
    )

    report = evaluate(silver_to_predictions(s), load_labels(labels_dir)) if labels_dir else None
    run_id = None
    if report is not None and track:
        from docintel.tracking import log_extraction_run

        first = s.select("llm_client", "llm_model").filter("llm_client is not null").first()
        run_id = log_extraction_run(
            report,
            prompt_version=prompt_version,
            client_name=first["llm_client"] if first else client_kind,
            model=first["llm_model"] if first else "unknown",
            experiment=experiment,
        )
    return RunResult(tables, report, run_id)  # type: ignore[arg-type]


def write_report(report: EvalReport, out_dir: str | Path) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "eval_report.md").write_text(report.to_markdown() + "\n", encoding="utf-8")
    (out / "eval_metrics.json").write_text(
        json.dumps(
            {"metrics": report.metrics(), "fields": report.table(), "per_doc": report.per_doc},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
