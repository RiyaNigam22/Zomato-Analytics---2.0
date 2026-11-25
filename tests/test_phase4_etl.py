"""Tests for Phase 4 automated ETL pipeline (full, incremental, idempotency, failure log)."""

from pathlib import Path
import pandas as pd
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from src.db.models import Base, DataQualityResult, EtlRunLog, FactMenuSnapshot
from src.etl.pipeline import run_etl_pipeline


def _make_csv(csv_path: Path) -> None:
    rows = [
        {
            "Restaurant_Name": "Spice Hub",
            "Dining_Rating": 4.3,
            "Delivery_Rating": 4.1,
            "Dining_Votes": 150,
            "Delivery_Votes": 100,
            "Cuisine": "North Indian",
            "Place_Name": "Indiranagar",
            "City": "Bengaluru",
            "Item_Name": "Paneer Tikka",
            "Best_Seller": "1",
            "Votes": 250,
            "Prices": 300.0,
            "Average_Rating": 4.2,
            "Total_Votes": 250,
            "Price_per_Vote": 1.2,
            "Log_Price": 5.7,
            "Is_Bestseller": 1,
            "Restaurant_Popularity": 0.9,
            "Avg_Rating_Restaurant": 4.2,
            "Avg_Price_Restaurant": 300.0,
            "Avg_Rating_Cuisine": 4.0,
            "Avg_Price_Cuisine": 280.0,
            "Avg_Rating_City": 4.1,
            "Avg_Price_City": 290.0,
            "Is_Highly_Rated": 1,
            "Is_Expensive": 0,
        },
        {
            "Restaurant_Name": "Spice Hub",
            "Dining_Rating": 4.3,
            "Delivery_Rating": 4.1,
            "Dining_Votes": 150,
            "Delivery_Votes": 100,
            "Cuisine": "North Indian",
            "Place_Name": "Indiranagar",
            "City": "Bengaluru",
            "Item_Name": "Garlic Naan",
            "Best_Seller": "0",
            "Votes": 120,
            "Prices": 60.0,
            "Average_Rating": 4.2,
            "Total_Votes": 120,
            "Price_per_Vote": 0.5,
            "Log_Price": 4.1,
            "Is_Bestseller": 1,
            "Restaurant_Popularity": 0.9,
            "Avg_Rating_Restaurant": 4.2,
            "Avg_Price_Restaurant": 300.0,
            "Avg_Rating_Cuisine": 4.0,
            "Avg_Price_Cuisine": 280.0,
            "Avg_Rating_City": 4.1,
            "Avg_Price_City": 290.0,
            "Is_Highly_Rated": 1,
            "Is_Expensive": 0,
        },
    ]
    pd.DataFrame(rows).to_csv(csv_path, index=False)


def test_etl_incremental_and_idempotent_replay(tmp_path: Path) -> None:
    csv_file = tmp_path / "zomato.csv"
    _make_csv(csv_file)
    orig_bytes = csv_file.read_bytes()

    db_path = tmp_path / "etl_idempotent.db"
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, future=True)

    res1 = run_etl_pipeline(
        csv_path=csv_file,
        quarantine_dir=tmp_path / "quarantine",
        log_dir=tmp_path / "logs",
        session_factory=factory,
        mode="incremental",
        offset=0,
        batch_size=1,
        snapshot_batch_id="batch-inc-1",
    )
    assert res1["status"] == "SUCCESS"
    assert res1["rows_read"] == 1
    assert res1["rows_upserted"] == 1

    res_replay = run_etl_pipeline(
        csv_path=csv_file,
        quarantine_dir=tmp_path / "quarantine",
        log_dir=tmp_path / "logs",
        session_factory=factory,
        mode="incremental",
        offset=0,
        batch_size=1,
        snapshot_batch_id="batch-inc-1",
    )
    assert res_replay["rows_upserted"] == 0

    with factory() as session:
        snap_count = session.scalars(select(FactMenuSnapshot)).all()
        dq_count = session.scalars(select(DataQualityResult)).all()
        run_count = session.scalars(select(EtlRunLog)).all()

    assert len(snap_count) == 1
    assert len(dq_count) >= 3
    assert len(run_count) == 2
    assert csv_file.read_bytes() == orig_bytes
    engine.dispose()


def test_etl_records_failed_run_on_missing_file(tmp_path: Path) -> None:
    db_path = tmp_path / "etl_fail.db"
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, future=True)

    with pytest.raises(FileNotFoundError):
        run_etl_pipeline(
            csv_path=tmp_path / "missing.csv",
            quarantine_dir=tmp_path / "quarantine",
            log_dir=tmp_path / "logs",
            session_factory=factory,
            mode="full",
            snapshot_batch_id="batch-fail-1",
        )

    with factory() as session:
        runs = session.scalars(select(EtlRunLog)).all()

    assert len(runs) == 1
    assert runs[0].status == "FAILED"
    engine.dispose()
