"""Document intelligence lakehouse on Azure Databricks.

Bronze (raw documents) -> Silver (validated, LLM-extracted fields) -> Gold (analytics
and quality metrics), with MLflow tracking extraction accuracy per prompt version.
"""

__version__ = "0.1.0"
