PY ?= python
export MLFLOW_DISABLE_AGENT_HINT=1

.PHONY: help install lint format test data run eval mlflow-ui infra-build bundle-validate deploy clean

help:  ## Show targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-16s %s\n", $$1, $$2}'

install:  ## Install package with local + dev extras (editable)
	$(PY) -m pip install -e ".[local,dev,pdf]"

lint:  ## Ruff lint + format check
	ruff check .
	ruff format --check .

format:  ## Auto-fix lint and format
	ruff check --fix .
	ruff format .

test:  ## Run pytest (PySpark local mode, needs Java 17)
	$(PY) -m pytest

data:  ## Regenerate synthetic sample documents + labels
	docintel generate --out data/sample

run:  ## Bronze -> silver -> gold locally + eval + MLflow (rule-based client)
	docintel run --client rule_based --prompt-version v2

eval: run  ## Alias for run; report lands in output/eval_report.md

mlflow-ui:  ## Browse local MLflow runs
	mlflow ui --backend-store-uri sqlite:///mlflow.db

infra-build:  ## Compile/lint Bicep (needs az CLI or bicep)
	az bicep build --file infra/main.bicep --stdout > /dev/null

bundle-validate:  ## Validate the Databricks Asset Bundle (needs databricks CLI auth)
	databricks bundle validate -t dev

deploy:  ## Deploy the bundle to the dev target
	databricks bundle deploy -t dev

clean:  ## Remove local outputs
	rm -rf output mlruns mlflow.db spark-warehouse dist build .pytest_cache .ruff_cache
