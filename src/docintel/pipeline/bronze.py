"""Bronze: land raw document bytes with lineage metadata, unchanged."""

from __future__ import annotations

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

SUPPORTED_GLOB = "*.{txt,md,json,pdf}"


def read_raw_documents(spark: SparkSession, path: str) -> DataFrame:
    """Batch-read documents as binary files (works for local paths, DBFS, ADLS abfss://)."""
    return (
        spark.read.format("binaryFile")
        .option("pathGlobFilter", SUPPORTED_GLOB)
        .option("recursiveFileLookup", "true")
        .load(path)
    )


def read_raw_documents_stream(spark: SparkSession, path: str) -> DataFrame:  # pragma: no cover
    """Incremental ingestion with Databricks Auto Loader (Databricks runtime only)."""
    return (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "binaryFile")
        .option("pathGlobFilter", SUPPORTED_GLOB)
        .option("recursiveFileLookup", "true")
        .load(path)
    )


def to_bronze(raw: DataFrame, ingest_run_id: str = "manual") -> DataFrame:
    """Normalize the binaryFile schema into the bronze_documents table schema."""
    file_name = F.regexp_extract(F.col("path"), r"([^/]+)$", 1)
    return raw.select(
        F.regexp_replace(file_name, r"\.[^.]+$", "").alias("doc_id"),
        F.col("path").alias("source_path"),
        F.lower(F.regexp_extract(file_name, r"\.([^.]+)$", 1)).alias("file_ext"),
        F.col("content"),
        F.col("length").alias("size_bytes"),
        F.col("modificationTime").alias("source_modified_at"),
        F.sha2(F.col("content"), 256).alias("content_sha256"),
        F.current_timestamp().alias("ingested_at"),
        F.lit(ingest_run_id).alias("ingest_run_id"),
    )


def dedupe_bronze(bronze: DataFrame) -> DataFrame:
    """Keep the latest copy of each distinct document (by content hash)."""
    return bronze.dropDuplicates(["content_sha256"])
