# Databricks notebook source
# MAGIC %md
# MAGIC # 02 · Silver: OCR + LLM extraction + schema validation
# MAGIC * Text extraction from raw bytes (plain text, OCR JSON, digital PDF).
# MAGIC * Structured extraction with the configured client (`azure_openai` or the offline
# MAGIC   `rule_based` baseline) and versioned prompt.
# MAGIC * Pydantic validation: invalid records are kept with their errors (quarantine view),
# MAGIC   business-rule issues are attached as `quality_issues`.
# MAGIC
# MAGIC Only documents whose `content_sha256` has not been processed with the current prompt
# MAGIC version are sent to the LLM, so re-runs do not re-pay for tokens.

# COMMAND ----------

# MAGIC %run ./_setup

# COMMAND ----------

from pyspark.sql import functions as F

from docintel.pipeline import silver

bronze = TARGET.read(spark, "bronze_documents").dropDuplicates(["content_sha256"])  # noqa: F821
silver_name = TARGET.name("silver_documents")

if spark.catalog.tableExists(silver_name):  # noqa: F821
    done = (
        spark.table(silver_name)  # noqa: F821
        .filter(F.col("prompt_version") == PROMPT_VERSION)
        .select("content_sha256")
    )
    bronze = bronze.join(done, "content_sha256", "left_anti")

todo = bronze.count()
print(f"{todo} new documents to extract with client={LLM_CLIENT} prompt={PROMPT_VERSION}")

# COMMAND ----------

if todo:
    # Bound LLM concurrency (and Azure OpenAI TPM usage) via the number of partitions.
    new_silver = silver.to_silver(
        bronze.repartition(LLM_PARTITIONS), client_kind=LLM_CLIENT, prompt_version=PROMPT_VERSION
    )
    (
        new_silver.write.format("delta")
        .mode("append")
        .option("mergeSchema", "true")
        .saveAsTable(silver_name)
    )

silver_all = spark.table(silver_name)  # noqa: F821
TARGET.write(silver.to_line_items(silver_all), "silver_line_items")
spark.sql(  # noqa: F821
    f"CREATE OR REPLACE VIEW {TARGET.name('silver_quarantine')} AS "
    f"SELECT doc_id, source_path, prompt_version, ocr_error, validation_errors, extracted_at "
    f"FROM {silver_name} WHERE NOT is_valid"
)

# COMMAND ----------

display(  # noqa: F821
    silver_all.groupBy("prompt_version", "doc_type", "is_valid").count().orderBy("prompt_version")
)
