"""Gold: business analytics and extraction-quality metrics."""

from __future__ import annotations

from pyspark.sql import DataFrame
from pyspark.sql import functions as F

from docintel.schemas import SCALAR_FIELDS


def vendor_spend(silver: DataFrame) -> DataFrame:
    """Monthly invoiced spend per vendor and currency (valid invoices only)."""
    return (
        silver.filter(F.col("is_valid") & (F.col("doc_type") == "invoice"))
        .withColumn("month", F.date_trunc("month", F.col("issue_date")).cast("date"))
        .groupBy("vendor_name", "currency", "month")
        .agg(
            F.count("*").alias("n_invoices"),
            F.sum("total").alias("total_amount"),
            F.sum("tax").alias("total_tax"),
            F.round(F.avg("total"), 2).alias("avg_invoice_amount"),
            F.min("due_date").alias("earliest_due_date"),
        )
        .orderBy("vendor_name", "currency", "month")
    )


def extraction_quality(silver: DataFrame) -> DataFrame:
    """Validity rate, review-flag rate and per-field fill rate by doc type / prompt."""
    fill = [
        F.round(F.avg(F.when(F.col(f).isNotNull(), 1.0).otherwise(0.0)), 4).alias(f"fill_{f}")
        for f in SCALAR_FIELDS
        if f != "doc_type"
    ]
    return (
        silver.withColumn("doc_type", F.coalesce("doc_type", F.lit("unknown")))
        .groupBy("doc_type", "prompt_version", "llm_client")
        .agg(
            F.count("*").alias("n_docs"),
            F.sum(F.col("is_valid").cast("int")).alias("n_valid"),
            F.round(F.avg(F.col("is_valid").cast("double")), 4).alias("valid_rate"),
            F.sum((F.size("quality_issues") > 0).cast("int")).alias("n_flagged_for_review"),
            F.round(F.avg(F.size("line_items").cast("double")), 2).alias("avg_line_items"),
            *fill,
        )
        .orderBy("doc_type", "prompt_version")
    )


def po_invoice_reconciliation(silver: DataFrame) -> DataFrame:
    """Match invoices to purchase orders by PO number (AP 2-way match signal)."""
    valid = silver.filter(F.col("is_valid"))
    inv = valid.filter(F.col("doc_type") == "invoice").select(
        F.col("doc_id").alias("invoice_doc_id"),
        F.col("document_number").alias("invoice_number"),
        F.col("vendor_name").alias("invoice_vendor"),
        "po_number",
        F.col("total").alias("invoice_total"),
        F.col("currency").alias("invoice_currency"),
    )
    po = valid.filter(F.col("doc_type") == "purchase_order").select(
        F.col("document_number").alias("po_number"),
        F.col("doc_id").alias("po_doc_id"),
        F.col("vendor_name").alias("po_vendor"),
        F.col("total").alias("po_total"),
    )
    return (
        inv.join(po, on="po_number", how="left")
        .withColumn(
            "match_status",
            F.when(F.col("po_number").isNull(), "no_po_reference")
            .when(F.col("po_doc_id").isNull(), "po_not_found")
            .when(F.col("po_vendor") != F.col("invoice_vendor"), "vendor_mismatch")
            .otherwise("matched"),
        )
        .orderBy("invoice_doc_id")
    )
