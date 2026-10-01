"""Command line entry point: ``docintel generate|run``."""

from __future__ import annotations

import argparse
import sys

from docintel.prompts import DEFAULT_PROMPT_VERSION, PROMPTS


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="docintel", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate", help="write synthetic sample documents + labels")
    g.add_argument("--out", default="data/sample")
    g.add_argument("--seed", type=int, default=42)

    r = sub.add_parser("run", help="run bronze -> silver -> gold locally and evaluate")
    r.add_argument("--raw", default="data/sample/raw")
    r.add_argument("--labels", default="data/sample/labels")
    r.add_argument("--out", default="output/lakehouse")
    r.add_argument("--client", default="rule_based", choices=["rule_based", "azure_openai"])
    r.add_argument("--prompt-version", default=DEFAULT_PROMPT_VERSION, choices=sorted(PROMPTS))
    r.add_argument("--format", default="parquet", choices=["parquet", "delta"])
    r.add_argument("--no-mlflow", action="store_true", help="skip MLflow logging")
    r.add_argument("--report-dir", default="output")

    args = parser.parse_args(argv)
    if args.cmd == "generate":
        from docintel.data_gen import write_sample

        docs = write_sample(args.out, seed=args.seed)
        print(f"wrote {len(docs)} documents to {args.out}/raw and labels to {args.out}/labels")
        return 0

    from pathlib import Path

    from docintel.pipeline.io import TableTarget, local_spark
    from docintel.runner import run_pipeline, write_report

    spark = local_spark()
    spark.sparkContext.setLogLevel("ERROR")
    try:
        res = run_pipeline(
            spark,
            str(Path(args.raw).resolve()),
            TableTarget(base_path=str(Path(args.out).resolve()), fmt=args.format),
            client_kind=args.client,
            prompt_version=args.prompt_version,
            labels_dir=args.labels,
            track=not args.no_mlflow,
        )
    finally:
        spark.stop()
    for name, loc in res.tables.items():
        print(f"{name:<32} -> {loc}")
    if res.report:
        write_report(res.report, args.report_dir)
        m = res.report.metrics()
        print()
        print(res.report.to_markdown())
        print(
            f"\ndocs={res.report.n_docs} schema_valid_rate={m['schema_valid_rate']:.3f} "
            f"doc_exact_match_rate={m['doc_exact_match_rate']:.3f}"
        )
    if res.run_id:
        print(f"MLflow run: {res.run_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
