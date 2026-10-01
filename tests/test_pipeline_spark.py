from pathlib import Path

import pytest
from pyspark.sql import functions as F

from docintel.pipeline import bronze, gold, silver
from docintel.pipeline.io import TableTarget
from docintel.runner import run_pipeline, silver_to_predictions


@pytest.fixture(scope="module")
def bronze_df(spark, sample_dir):
    raw = bronze.read_raw_documents(spark, str(sample_dir / "raw"))
    return bronze.dedupe_bronze(bronze.to_bronze(raw, ingest_run_id="test")).cache()


@pytest.fixture(scope="module")
def silver_df(bronze_df):
    return silver.to_silver(bronze_df, client_kind="rule_based", prompt_version="v2").cache()


def test_bronze_schema_and_lineage(bronze_df):
    assert bronze_df.count() == 24
    row = bronze_df.filter(F.col("doc_id") == "inv_001").first()
    assert row.file_ext == "txt" and len(row.content_sha256) == 64
    assert row.ingest_run_id == "test" and row.size_bytes > 0


def test_bronze_dedupes_identical_content(spark, bronze_df):
    doubled = bronze_df.unionByName(bronze_df)
    assert bronze.dedupe_bronze(doubled).count() == 24


def test_silver_extraction(silver_df):
    assert silver_df.count() == 24
    assert silver_df.filter("ocr_error is not null").count() == 0
    po = silver_df.filter(F.col("doc_id") == "po_001").first()
    assert po.doc_type == "purchase_order" and po.is_valid and po.prompt_version == "v2"
    assert po.llm_client == "rule_based"
    assert len(po.line_items) >= 1
    types = {r.doc_type for r in silver_df.select("doc_type").distinct().collect()}
    assert types == {"invoice", "purchase_order", "contract"}


def test_silver_quarantines_unparseable(spark):
    df = spark.createDataFrame(
        [("bad", "/x/bad.txt", bytearray(b"lorem ipsum")), ("img", "/x/img.png", bytearray(b"x"))],
        "doc_id string, source_path string, content binary",
    ).withColumn("content_sha256", F.sha2("content", 256))
    s = silver.to_silver(df)
    valid, quarantine = silver.valid_and_quarantine(s)
    assert valid.count() == 0 and quarantine.count() == 2
    img = quarantine.filter("doc_id = 'img'").first()
    assert img.ocr_error.startswith("UnsupportedDocumentError")
    assert img.validation_errors == ["no_text"]


def test_line_items_and_gold(silver_df):
    items = silver.to_line_items(silver_df)
    assert items.count() > 0 and items.filter("amount < 0").count() == 0

    spend = gold.vendor_spend(silver_df)
    assert spend.count() > 0
    assert (
        spend.agg(F.sum("n_invoices")).first()[0]
        == silver_df.filter("is_valid and doc_type = 'invoice'").count()
    )

    quality = {r.doc_type: r for r in gold.extraction_quality(silver_df).collect()}
    assert set(quality) == {"invoice", "purchase_order", "contract"}
    assert quality["invoice"].n_docs == 12

    recon = gold.po_invoice_reconciliation(silver_df)
    statuses = {r.match_status for r in recon.collect()}
    assert "matched" in statuses
    assert statuses <= {"matched", "po_not_found", "vendor_mismatch", "no_po_reference"}


def test_end_to_end_local_run_with_mlflow(spark, sample_dir, tmp_path, monkeypatch):
    monkeypatch.setenv("MLFLOW_TRACKING_URI", f"sqlite:///{tmp_path / 'mlflow.db'}")
    target = TableTarget(base_path=str(tmp_path / "lake"), fmt="parquet")
    res = run_pipeline(
        spark,
        str(sample_dir / "raw"),
        target,
        labels_dir=str(sample_dir / "labels"),
        track=True,
        experiment="docintel-test",
    )
    assert set(res.tables) == {
        "bronze_documents",
        "silver_documents",
        "silver_line_items",
        "gold_vendor_spend",
        "gold_extraction_quality",
        "gold_po_invoice_reconciliation",
    }
    assert all(Path(p).exists() for p in res.tables.values())
    m = res.report.metrics()
    assert m["n_docs"] == 24
    # The rule-based baseline is good but not perfect on OCR-noisy documents.
    assert 0.8 < m["micro_f1"] < 1.0

    import mlflow

    run = mlflow.get_run(res.run_id)
    assert run.data.params["prompt_version"] == "v2"
    assert run.data.params["llm_client"] == "rule_based"
    assert run.data.metrics["micro_f1"] == pytest.approx(m["micro_f1"])
    preds = silver_to_predictions(target.read(spark, "silver_documents"))
    assert len(preds) == 24
