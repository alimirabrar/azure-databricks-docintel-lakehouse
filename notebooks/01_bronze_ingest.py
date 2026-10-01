# Databricks notebook source
# MAGIC %md
# MAGIC # 01 · Bronze: ingest raw documents
# MAGIC Incrementally loads invoices / POs / contracts from the ADLS landing zone (or a UC
# MAGIC volume) with **Auto Loader** (`binaryFile`), keeping the raw bytes plus lineage
# MAGIC (path, size, modification time, SHA-256, ingest run id) in `bronze_documents`.

# COMMAND ----------

# MAGIC %run ./_setup

# COMMAND ----------

from docintel.pipeline.bronze import read_raw_documents_stream, to_bronze

run_id = spark.conf.get("spark.databricks.job.runId", "interactive")  # noqa: F821
checkpoint = f"/Volumes/{CATALOG}/{SCHEMA}/landing/_checkpoints/bronze_documents"

query = (
    to_bronze(read_raw_documents_stream(spark, LANDING_PATH), ingest_run_id=run_id)  # noqa: F821
    .writeStream.option("checkpointLocation", checkpoint)
    .trigger(availableNow=True)
    .toTable(TARGET.name("bronze_documents"))
)
query.awaitTermination()

# COMMAND ----------

display(  # noqa: F821
    spark.sql(  # noqa: F821
        f"SELECT ingest_run_id, file_ext, count(*) AS n, sum(size_bytes) AS bytes "
        f"FROM {TARGET.name('bronze_documents')} GROUP BY ALL ORDER BY ALL"
    )
)
