"""Database loading and idempotent upsert logic for dimensions, facts, DQ, and run logs."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from src.db.models import (
    DataQualityResult,
    DimCuisine,
    DimLocation,
    DimMenuItem,
    DimRestaurant,
    EtlRunLog,
    FactMenuSnapshot,
)

logger = logging.getLogger("zomato_etl")


def create_run_log(
    session: Session,
    *,
    pipeline_mode: str,
    source_name: str,
    snapshot_batch_id: str,
) -> EtlRunLog:
    run = EtlRunLog(
        pipeline_mode=pipeline_mode,
        source_name=source_name,
        snapshot_batch_id=snapshot_batch_id,
        status="RUNNING",
        started_at=datetime.now(timezone.utc),
    )
    session.add(run)
    session.flush()
    return run


def finalize_run_log(
    session: Session,
    run: EtlRunLog,
    *,
    status: str,
    rows_read: int,
    rows_quarantined: int,
    rows_upserted: int,
    error_message: str | None = None,
) -> None:
    run.status = status
    run.ended_at = datetime.now(timezone.utc)
    run.rows_read = rows_read
    run.rows_quarantined = rows_quarantined
    run.rows_upserted = rows_upserted
    run.error_message = error_message[:4000] if error_message else None
    session.flush()


def record_dq_checks(
    session: Session,
    *,
    run_id: int | None,
    dataset_scope: str,
    checks: list[dict[str, Any]],
) -> None:
    for chk in checks:
        session.add(
            DataQualityResult(
                run_id=run_id,
                checked_at=datetime.now(timezone.utc),
                dataset_scope=dataset_scope,
                check_name=chk["check_name"],
                status=chk["status"],
                failed_rows=int(chk.get("failed_rows", 0)),
                details_json=chk.get("details_json"),
            )
        )
    session.flush()


def _load_dimension_caches(
    session: Session,
) -> tuple[
    dict[tuple[str, str], int],
    dict[str, int],
    dict[tuple[str, int], int],
    dict[tuple[int, str], int],
]:
    loc_cache: dict[tuple[str, str], int] = {
        (row.city_clean, row.place_name_clean): int(row.location_id)
        for row in session.execute(
            select(DimLocation.location_id, DimLocation.city_clean, DimLocation.place_name_clean)
        ).all()
    }
    cui_cache: dict[str, int] = {
        row.cuisine_clean: int(row.cuisine_id)
        for row in session.execute(select(DimCuisine.cuisine_id, DimCuisine.cuisine_clean)).all()
    }
    rest_cache: dict[tuple[str, int], int] = {
        (row.restaurant_name_clean, int(row.location_id)): int(row.restaurant_id)
        for row in session.execute(
            select(DimRestaurant.restaurant_id, DimRestaurant.restaurant_name_clean, DimRestaurant.location_id)
        ).all()
    }
    item_cache: dict[tuple[int, str], int] = {
        (int(row.restaurant_id), row.item_name_clean): int(row.menu_item_id)
        for row in session.execute(
            select(DimMenuItem.menu_item_id, DimMenuItem.restaurant_id, DimMenuItem.item_name_clean)
        ).all()
    }
    return loc_cache, cui_cache, rest_cache, item_cache


def upsert_snapshots(
    session: Session,
    *,
    run_id: int,
    records: list[dict[str, Any]],
    chunk_size: int = 500,
) -> int:
    """Resolve dimensions in bulk and idempotently load fact_menu_snapshot rows in chunks."""
    if not records:
        return 0

    loc_cache, cui_cache, rest_cache, item_cache = _load_dimension_caches(session)

    new_locs: dict[tuple[str, str], DimLocation] = {}
    for r in records:
        key = (r["city_clean"], r["place_name_clean"])
        if key not in loc_cache and key not in new_locs:
            new_locs[key] = DimLocation(
                city_clean=r["city_clean"],
                place_name_clean=r["place_name_clean"],
                city_raw=r["city_raw"],
                place_name_raw=r["place_name_raw"],
            )
    if new_locs:
        session.add_all(list(new_locs.values()))
        session.flush()
        for key, obj in new_locs.items():
            loc_cache[key] = int(obj.location_id)

    new_cuisines: dict[str, DimCuisine] = {}
    for r in records:
        key = r["cuisine_clean"]
        if key not in cui_cache and key not in new_cuisines:
            new_cuisines[key] = DimCuisine(cuisine_clean=r["cuisine_clean"], cuisine_raw=r["cuisine_raw"])
    if new_cuisines:
        session.add_all(list(new_cuisines.values()))
        session.flush()
        for key, obj in new_cuisines.items():
            cui_cache[key] = int(obj.cuisine_id)

    new_rests: dict[tuple[str, int], DimRestaurant] = {}
    for r in records:
        loc_id = loc_cache[(r["city_clean"], r["place_name_clean"])]
        cui_id = cui_cache[r["cuisine_clean"]]
        key = (r["restaurant_name_clean"], loc_id)
        if key not in rest_cache and key not in new_rests:
            new_rests[key] = DimRestaurant(
                restaurant_name_clean=r["restaurant_name_clean"],
                restaurant_name_raw=r["restaurant_name_raw"],
                location_id=loc_id,
                primary_cuisine_id=cui_id,
                source_name=r["source_name"],
            )
    if new_rests:
        session.add_all(list(new_rests.values()))
        session.flush()
        for key, obj in new_rests.items():
            rest_cache[key] = int(obj.restaurant_id)

    new_items: dict[tuple[int, str], DimMenuItem] = {}
    for r in records:
        loc_id = loc_cache[(r["city_clean"], r["place_name_clean"])]
        rest_id = rest_cache[(r["restaurant_name_clean"], loc_id)]
        key = (rest_id, r["item_name_clean"])
        if key not in item_cache and key not in new_items:
            item_raw_val = r.get("item_raw") if r.get("item_raw") is not None else r.get("item_name_raw")
            new_items[key] = DimMenuItem(
                restaurant_id=rest_id,
                item_name_clean=r["item_name_clean"],
                item_name_raw=item_raw_val,
            )
    if new_items:
        session.add_all(list(new_items.values()))
        session.flush()
        for key, obj in new_items.items():
            item_cache[key] = int(obj.menu_item_id)

    deduped_fact_map: dict[str, dict[str, Any]] = {}
    for r in records:
        loc_id = loc_cache[(r["city_clean"], r["place_name_clean"])]
        cui_id = cui_cache[r["cuisine_clean"]]
        rest_id = rest_cache[(r["restaurant_name_clean"], loc_id)]
        item_id = item_cache[(rest_id, r["item_name_clean"])]
        fp = r["row_fingerprint"]
        if fp not in deduped_fact_map:
            deduped_fact_map[fp] = {
                "run_id": run_id,
                "snapshot_batch_id": r["snapshot_batch_id"],
                "observed_at": r["observed_at"],
                "source_name": r["source_name"],
                "row_fingerprint": fp,
                "restaurant_id": rest_id,
                "menu_item_id": item_id,
                "location_id": loc_id,
                "cuisine_id": cui_id,
                "price": r["price"],
                "log_price": r["log_price"],
                "price_per_vote": r["price_per_vote"],
                "dining_rating": r["dining_rating"],
                "delivery_rating": r["delivery_rating"],
                "average_rating": r["average_rating"],
                "dining_votes": r["dining_votes"],
                "delivery_votes": r["delivery_votes"],
                "votes": r["votes"],
                "total_votes": r["total_votes"],
                "best_seller_raw": r["best_seller_raw"],
                "is_bestseller": r["is_bestseller"],
                "restaurant_popularity": r["restaurant_popularity"],
                "is_highly_rated": r["is_highly_rated"],
                "is_expensive": r["is_expensive"],
            }

    fact_rows = list(deduped_fact_map.values())
    dialect_name = session.get_bind().dialect.name
    inserted_total = 0

    for start in range(0, len(fact_rows), chunk_size):
        chunk = fact_rows[start : start + chunk_size]
        if dialect_name == "postgresql":
            stmt = (
                pg_insert(FactMenuSnapshot)
                .values(chunk)
                .on_conflict_do_nothing(constraint="uq_fact_snapshot_batch_fingerprint")
            )
            result = session.execute(stmt)
            rc = getattr(result, "rowcount", None)
            inserted_total += int(rc if rc is not None and rc >= 0 else len(chunk))
        else:
            existing_fps = {
                row[0]
                for row in session.execute(
                    select(FactMenuSnapshot.row_fingerprint).where(
                        FactMenuSnapshot.snapshot_batch_id == chunk[0]["snapshot_batch_id"],
                        FactMenuSnapshot.row_fingerprint.in_([c["row_fingerprint"] for c in chunk]),
                    )
                ).all()
            }
            new_fact_objs = [FactMenuSnapshot(**c) for c in chunk if c["row_fingerprint"] not in existing_fps]
            if new_fact_objs:
                session.add_all(new_fact_objs)
                inserted_total += len(new_fact_objs)

        session.flush()
        logger.info("Loaded snapshot chunk %s..%s of %s", start, min(start + chunk_size, len(fact_rows)), len(fact_rows))

    return inserted_total

