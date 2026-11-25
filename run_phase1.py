"""CLI entry point for Phase 1 baseline validation, cleaning, and DQ reporting."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import load_config
from src.processing.cleaner import clean_and_report


def parse_args() -> argparse.Namespace:
    cfg = load_config(PROJECT_ROOT)
    parser = argparse.ArgumentParser(description="Run Zomato Analytics 2.0 Phase 1 pipeline.")
    parser.add_argument(
        "--raw-csv",
        type=Path,
        default=cfg.raw_csv_path,
        help="Path to raw input CSV file (never modified).",
    )
    parser.add_argument(
        "--processed-dir",
        type=Path,
        default=cfg.processed_dir,
        help="Directory for cleaned baseline output and DQ reports.",
    )
    parser.add_argument(
        "--quarantine-dir",
        type=Path,
        default=cfg.quarantine_dir,
        help="Directory for quarantined anomalous rows.",
    )
    parser.add_argument(
        "--drop-exact-duplicates",
        action="store_true",
        help="Optionally deduplicate exact rows after logging counts (default: False).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.raw_csv.exists():
        raise FileNotFoundError(f"Raw CSV not found at: {args.raw_csv}")

    report = clean_and_report(
        raw_csv_path=args.raw_csv,
        processed_dir=args.processed_dir,
        quarantine_dir=args.quarantine_dir,
        drop_exact_duplicates=args.drop_exact_duplicates,
    )
    print(f"Phase 1 complete. Processed rows: {report['post_cleaning_validation']['row_count']:,}")
    print(f"DQ report written to: {args.processed_dir / 'data_quality_report.md'}")


if __name__ == "__main__":
    main()
