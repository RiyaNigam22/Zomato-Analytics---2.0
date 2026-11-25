"""CLI entry point for Phase 5 SQL analytical views and business insights export."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.analytics.queries import run_all_analytics_and_export
from src.config import load_config


def parse_args() -> argparse.Namespace:
    cfg = load_config(PROJECT_ROOT)
    parser = argparse.ArgumentParser(description="Run Zomato Analytics 2.0 Phase 5 SQL analytics.")
    parser.add_argument(
        "--views-file",
        type=Path,
        default=PROJECT_ROOT / "sql" / "views" / "analytics_views.sql",
        help="Path to SQL analytical views definition file.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=cfg.processed_dir / "analytics",
        help="Directory for exported query CSVs and business insights report.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    res = run_all_analytics_and_export(
        views_sql_path=args.views_file,
        output_dir=args.output_dir,
    )
    print(f"Phase 5 complete. Exported {res['query_count']} analytical datasets -> {res['output_dir']}")
    print(f"Business insights report: {res['report_path']}")


if __name__ == "__main__":
    main()
