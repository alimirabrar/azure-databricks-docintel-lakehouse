# Databricks notebook source
# MAGIC %md
# MAGIC # 03 · Gold: analytics & data-quality metrics
# MAGIC * `gold_vendor_spend` – monthly invoiced spend per vendor / currency
# MAGIC * `gold_extraction_quality` – validity, review-flag and per-field fill rates by doc type
# MAGIC   and prompt version
# MAGIC * `gold_po_invoice_reconciliation` – invoice → PO matching (AP 2-way match signal)

# COMMAND ----------

# MAGIC %run ./_setup

# COMMAND ----------

from pyspark.sql import functions as F
from pyspark.sql.window import Window

from docintel.pipeline import gold

silver_all = TARGET.read(spark, "silver_documents")  # noqa: F821
# Business tables use the latest extraction of each document.
w = Window.partitionBy("content_sha256").orderBy(F.col("extracted_at").desc())
latest = silver_all.withColumn("_rn", F.row_number().over(w)).filter("_rn = 1").drop("_rn")

TARGET.write(gold.vendor_spend(latest), "gold_vendor_spend")
TARGET.write(gold.po_invoice_reconciliation(latest), "gold_po_invoice_reconciliation")
# Quality metrics keep every prompt version for side-by-side comparison.
TARGET.write(gold.extraction_quality(silver_all), "gold_extraction_quality")

# COMMAND ----------

display(spark.table(TARGET.name("gold_extraction_quality")))  # noqa: F821
