"""Silver: text extraction (OCR step) + LLM structured extraction + Pydantic validation."""

from __future__ import annotations

from typing import Any

from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql import types as T

from docintel.prompts import DEFAULT_PROMPT_VERSION

MONEY = T.DecimalType(18, 2)

LINE_ITEM_TYPE = T.StructType(
    [
        T.StructField("description", T.StringType()),
        T.StructField("quantity", MONEY),
        T.StructField("unit_price", MONEY),
        T.StructField("amount", MONEY),
    ]
)

TEXT_RESULT_TYPE = T.StructType(
    [T.StructField("text", T.StringType()), T.StructField("ocr_error", T.StringType())]
)

EXTRACTION_TYPE = T.StructType(
    [
        T.StructField("is_valid", T.BooleanType()),
        T.StructField("validation_errors", T.ArrayType(T.StringType())),
        T.StructField("quality_issues", T.ArrayType(T.StringType())),
        T.StructField("prompt_version", T.StringType()),
        T.StructField("llm_client", T.StringType()),
        T.StructField("llm_model", T.StringType()),
        T.StructField("doc_type", T.StringType()),
        T.StructField("document_number", T.StringType()),
        T.StructField("vendor_name", T.StringType()),
        T.StructField("buyer_name", T.StringType()),
        T.StructField("issue_date", T.DateType()),
        T.StructField("due_date", T.DateType()),
        T.StructField("po_number", T.StringType()),
        T.StructField("currency", T.StringType()),
        T.StructField("subtotal", MONEY),
        T.StructField("tax", MONEY),
        T.StructField("total", MONEY),
        T.StructField("line_items", T.ArrayType(LINE_ITEM_TYPE)),
    ]
)

PAYLOAD_FIELDS = [f.name for f in EXTRACTION_TYPE.fields[6:]]

# One client per Python worker process (avoids pickling SDK clients into closures).
_CLIENTS: dict[str, Any] = {}


def _client(kind: str) -> Any:
    if kind not in _CLIENTS:
        from docintel.llm import get_client

        _CLIENTS[kind] = get_client(kind)
    return _CLIENTS[kind]


def _extract_text_row(content: bytearray | None, path: str) -> tuple[str | None, str | None]:
    from docintel.text_extraction import extract_text

    if content is None:
        return None, "empty_content"
    try:
        return extract_text(bytes(content), path), None
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def with_text(bronze: DataFrame) -> DataFrame:
    """Add ``text`` / ``ocr_error`` columns from the raw bytes."""
    udf = F.udf(_extract_text_row, TEXT_RESULT_TYPE)
    return (
        bronze.withColumn("_t", udf("content", "source_path"))
        .withColumn("text", F.col("_t.text"))
        .withColumn("ocr_error", F.col("_t.ocr_error"))
        .drop("_t")
    )


def _extract_fields_fn(client_kind: str, prompt_version: str):
    def run(text: str | None) -> dict[str, Any]:
        from docintel.extraction import extract_document

        base: dict[str, Any] = {"prompt_version": prompt_version}
        if not text:
            return {
                **base,
                "is_valid": False,
                "validation_errors": ["no_text"],
                "quality_issues": [],
            }
        client = _client(client_kind)
        res = extract_document(text, client, prompt_version)
        out = {
            **base,
            "is_valid": res.is_valid,
            "validation_errors": res.errors,
            "quality_issues": res.issues,
            "llm_client": res.client,
            "llm_model": res.model,
        }
        if res.is_valid and res.payload is not None:
            from docintel.schemas import DocumentExtraction

            model = DocumentExtraction.model_validate(res.payload)
            out.update(model.model_dump(mode="python"))
        return out

    return run


def to_silver(
    bronze: DataFrame,
    client_kind: str = "rule_based",
    prompt_version: str = DEFAULT_PROMPT_VERSION,
) -> DataFrame:
    """bronze_documents -> silver_documents (one row per document, valid or not)."""
    udf = F.udf(_extract_fields_fn(client_kind, prompt_version), EXTRACTION_TYPE)
    df = with_text(bronze).withColumn("_x", udf("text"))
    return df.select(
        "doc_id",
        "source_path",
        "content_sha256",
        "text",
        "ocr_error",
        *[F.col(f"_x.{f.name}").alias(f.name) for f in EXTRACTION_TYPE.fields],
        F.current_timestamp().alias("extracted_at"),
    )


def valid_and_quarantine(silver: DataFrame) -> tuple[DataFrame, DataFrame]:
    return silver.filter(F.col("is_valid")), silver.filter(~F.col("is_valid"))


def to_line_items(silver: DataFrame) -> DataFrame:
    """Explode validated line items into silver_line_items."""
    return (
        silver.filter(F.col("is_valid"))
        .select(
            "doc_id",
            "doc_type",
            "document_number",
            "vendor_name",
            "currency",
            "issue_date",
            F.posexplode("line_items").alias("line_no", "item"),
        )
        .select(
            "doc_id",
            "doc_type",
            "document_number",
            "vendor_name",
            "currency",
            "issue_date",
            (F.col("line_no") + 1).alias("line_no"),
            F.col("item.description").alias("description"),
            F.col("item.quantity").alias("quantity"),
            F.col("item.unit_price").alias("unit_price"),
            F.col("item.amount").alias("amount"),
        )
    )
