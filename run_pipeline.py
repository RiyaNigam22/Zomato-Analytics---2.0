"""Central CLI entry point for Zomato Analytics 2.0 ETL pipeline."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import load_config
from src.etl.pipeline import run_etl_pipeline


def parse_args() -> argparse.Namespace:
    cfg = load_config(PROJECT_ROOT)
    parser = argparse.ArgumentParser(description="Run Zomato Analytics 2.0 Automated ETL Pipeline.")
    parser.add_argument(
        "--mode",
        choices=["full", "incremental"],
        default="incremental",
        help="Execution mode: 'full' for complete dataset load, 'incremental' for batch slice.",
    )
    parser.add_argument(
        "--csv-path",
        type=Path,
        default=cfg.raw_csv_path,
        help="Path to existing Zomato CSV file (never modified).",
    )
    parser.add_argument(
        "--offset",
        type=int,
        default=0,
        help="Starting row index for batch slicing (default: 0).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="Number of rows to process in this execution (incremental defaults to 5000).",
    )
    parser.add_argument(
        "--batch-id",
        type=str,
        default=None,
        help="Optional explicit snapshot batch ID for idempotent replay.",
    )
    parser.add_argument(
        "--source-name",
        type=str,
        default="baseline_csv",
        help="Source label recorded on snapshots and run logs.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg = load_config(PROJECT_ROOT)
    log_dir = Path(os.getenv("LOG_DIR", str(PROJECT_ROOT / "logs")))
    if not log_dir.is_absolute():
        log_dir = PROJECT_ROOT / log_dir

    result = run_etl_pipeline(
        csv_path=args.csv_path,
        quarantine_dir=cfg.quarantine_dir,
        log_dir=log_dir,
        mode=args.mode,
        offset=args.offset,
        batch_size=args.batch_size,
        snapshot_batch_id=args.batch_id,
        source_name=args.source_name,
        log_level=cfg.log_level,
    )
    print(
        f"ETL {result['status']} | batch_id={result['snapshot_batch_id']} | "
        f"read={result['rows_read']} | quarantined={result['rows_quarantined']} | upserted={result['rows_upserted']}"
    )


if __name__ == "__main__":
    main()
