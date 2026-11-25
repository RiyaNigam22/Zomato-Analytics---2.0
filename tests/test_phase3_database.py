"""Database tests for Phase 3 models, connection builder, and schema definition."""

from pathlib import Path
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.db.connection import build_database_url
from src.db.models import Base, DimCuisine, DimLocation, DimMenuItem, DimRestaurant, EtlRunLog, FactMenuSnapshot


def test_build_database_url_uses_env_without_hardcoded_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DB_HOST", "localhost")
    monkeypatch.setenv("DB_PORT", "5432")
    monkeypatch.setenv("DB_NAME", "zomato_db")
    monkeypatch.setenv("DB_USER", "analyst")
    monkeypatch.setenv("DB_PASSWORD", "s3cr3t@pass")

    url = build_database_url()
    assert url == "postgresql+psycopg://analyst:s3cr3t%40pass@localhost:5432/zomato_db"


def test_build_database_url_raises_when_password_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DB_PASSWORD", "")
    with pytest.raises(ValueError):
        build_database_url()


def test_orm_relationships_and_tables_in_sqlite_memory() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)

    with Session(engine) as session:
        loc = DimLocation(city_clean="Bengaluru", place_name_clean="Indiranagar")
        cuisine = DimCuisine(cuisine_clean="North Indian")
        session.add_all([loc, cuisine])
        session.flush()

        rest = DimRestaurant(
            restaurant_name_clean="Spice Hub",
            location_id=loc.location_id,
            primary_cuisine_id=cuisine.cuisine_id,
            source_name="baseline_csv",
        )
        session.add(rest)
        session.flush()

        item = DimMenuItem(restaurant_id=rest.restaurant_id, item_name_clean="Paneer Butter Masala")
        run = EtlRunLog(pipeline_mode="full", source_name="baseline_csv", snapshot_batch_id="batch-001", status="SUCCESS")
        session.add_all([item, run])
        session.flush()

        snap = FactMenuSnapshot(
            run_id=run.run_id,
            snapshot_batch_id="batch-001",
            observed_at=run.started_at,
            source_name="baseline_csv",
            row_fingerprint="a" * 64,
            restaurant_id=rest.restaurant_id,
            menu_item_id=item.menu_item_id,
            location_id=loc.location_id,
            cuisine_id=cuisine.cuisine_id,
            price=280.0,
            average_rating=4.2,
        )
        session.add(snap)
        session.commit()

        assert session.query(FactMenuSnapshot).count() == 1
        assert len(rest.menu_items) == 1
