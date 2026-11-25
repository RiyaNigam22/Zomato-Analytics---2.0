"""Orchestrator for Extract -> Transform -> Validate -> Load -> Log on existing Zomato CSV."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import pandas as pd
from sqlalchemy.orm import Session, sessionmaker

from src.db.connection import session_scope
from src.db.models import EtlRunLog
from src.etl.common import setup_logger
from src.etl.loader import create_run_log, finalize_run_log, record_dq_checks, upsert_snapshots
from src.etl.transformer import prepare_records


def slice_dataset(
    df: pd.DataFrame,
    *,
    mode: str,
    offset: int = 0,
    batch_size: int | None = None,
) -> pd.DataFrame:
    if mode == "full":
        if batch_size is not None and batch_size > 0:
            return df.iloc[offset : offset + batch_size].copy()
        return df.iloc[offset:].copy()
    if mode == "incremental":
        eff_batch = batch_size if (batch_size is not None and batch_size > 0) else 5000
        return df.iloc[offset : offset + eff_batch].copy()
    raise ValueError(f"Unsupported pipeline mode: {mode}. Expected 'full' or 'incremental'.")


def run_etl_pipeline(
    *,
    csv_path: Path,
    quarantine_dir: Path,
    log_dir: Path,
    session_factory: sessionmaker[Session] | None = None,
    mode: str = "full",
    offset: int = 0,
    batch_size: int | None = None,
    snapshot_batch_id: str | None = None,
    source_name: str = "baseline_csv",
    log_level: str = "INFO",
) -> dict[str, Any]:
    logger = setup_logger(log_dir, log_level=log_level)
    now_utc = datetime.now(timezone.utc)
    batch_id = snapshot_batch_id or f"{mode}_{now_utc.strftime('%Y%m%dT%H%M%SZ')}"
    quarantine_dir.mkdir(parents=True, exist_ok=True)

    with session_scope(session_factory) as start_session:
        start_log = create_run_log(
            start_session,
            pipeline_mode=mode,
            source_name=source_name,
            snapshot_batch_id=batch_id,
        )
        run_id = int(start_log.run_id)

    logger.info("Started ETL run_id=%s mode=%s batch_id=%s", run_id, mode, batch_id)

    try:
        if not csv_path.exists():
            raise FileNotFoundError(f"Input Zomato CSV not found: {csv_path}")

        full_df = pd.read_csv(csv_path, low_memory=False)
        df_slice = slice_dataset(full_df, mode=mode, offset=offset, batch_size=batch_size)
        rows_read = int(len(df_slice))

        records, quarantined_df, dq_bundle = prepare_records(
            df_slice,
            snapshot_batch_id=batch_id,
            observed_at=now_utc,
            source_name=source_name,
        )

        rows_quarantined = int(len(quarantined_df))
        if rows_quarantined > 0:
            q_file = quarantine_dir / f"quarantine_{batch_id}.csv"
            quarantined_df.to_csv(q_file, index=False)
            logger.warning("Quarantined %s rows to %s", rows_quarantined, q_file)

        with session_scope(session_factory) as work_session:
            run_log = work_session.get(EtlRunLog, run_id)
            if run_log is None:
                raise RuntimeError(f"ETL run_id={run_id} not found after start commit.")

            record_dq_checks(
                work_session,
                run_id=run_id,
                dataset_scope=f"{source_name}:{mode}",
                checks=dq_bundle["checks"],
            )

            rows_upserted = upsert_snapshots(work_session, run_id=run_id, records=records)
            finalize_run_log(
                work_session,
                run_log,
                status="SUCCESS",
                rows_read=rows_read,
                rows_quarantined=rows_quarantined,
                rows_upserted=rows_upserted,
            )

        logger.info(
            "Completed ETL run_id=%s status=SUCCESS read=%s quarantined=%s upserted=%s",
            run_id,
            rows_read,
            rows_quarantined,
            rows_upserted,
        )
        return {
            "run_id": run_id,
            "snapshot_batch_id": batch_id,
            "status": "SUCCESS",
            "rows_read": rows_read,
            "rows_quarantined": rows_quarantined,
            "rows_upserted": rows_upserted,
        }
    except Exception as exc:
        with session_scope(session_factory) as err_session:
            err_run = err_session.get(EtlRunLog, run_id)
            if err_run is not None:
                finalize_run_log(
                    err_session,
                    err_run,
                    status="FAILED",
                    rows_read=0,
                    rows_quarantined=0,
                    rows_upserted=0,
                    error_message=str(exc),
                )
        logger.exception("ETL run_id=%s failed: %s", run_id, exc)
        raise
