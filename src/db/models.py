"""SQLAlchemy ORM models for Zomato Analytics 2.0 PostgreSQL schema."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from sqlalchemy import (
    CHAR,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class DimLocation(Base):
    __tablename__ = "dim_location"
    __table_args__ = (UniqueConstraint("city_clean", "place_name_clean", name="uq_dim_location_city_place"),)

    location_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    city_clean: Mapped[str] = mapped_column(String(120), nullable=False)
    place_name_clean: Mapped[str] = mapped_column(String(180), nullable=False)
    city_raw: Mapped[str | None] = mapped_column(String(120), nullable=True)
    place_name_raw: Mapped[str | None] = mapped_column(String(180), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    restaurants: Mapped[list[DimRestaurant]] = relationship(back_populates="location")


class DimCuisine(Base):
    __tablename__ = "dim_cuisine"
    __table_args__ = (UniqueConstraint("cuisine_clean", name="uq_dim_cuisine_clean"),)

    cuisine_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    cuisine_clean: Mapped[str] = mapped_column(String(180), nullable=False)
    cuisine_raw: Mapped[str | None] = mapped_column(String(180), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    restaurants: Mapped[list[DimRestaurant]] = relationship(back_populates="primary_cuisine")


class DimRestaurant(Base):
    __tablename__ = "dim_restaurant"
    __table_args__ = (
        UniqueConstraint("restaurant_name_clean", "location_id", name="uq_dim_restaurant_name_loc"),
    )

    restaurant_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    restaurant_name_clean: Mapped[str] = mapped_column(String(255), nullable=False)
    restaurant_name_raw: Mapped[str | None] = mapped_column(String(255), nullable=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("dim_location.location_id", ondelete="RESTRICT"), nullable=False)
    primary_cuisine_id: Mapped[int | None] = mapped_column(
        ForeignKey("dim_cuisine.cuisine_id", ondelete="SET NULL"), nullable=True
    )
    source_name: Mapped[str] = mapped_column(String(64), nullable=False, default="baseline_csv")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    location: Mapped[DimLocation] = relationship(back_populates="restaurants")
    primary_cuisine: Mapped[DimCuisine | None] = relationship(back_populates="restaurants")
    menu_items: Mapped[list[DimMenuItem]] = relationship(back_populates="restaurant")


class DimMenuItem(Base):
    __tablename__ = "dim_menu_item"
    __table_args__ = (
        UniqueConstraint("restaurant_id", "item_name_clean", name="uq_dim_menu_item_rest_item"),
    )

    menu_item_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    restaurant_id: Mapped[int] = mapped_column(
        ForeignKey("dim_restaurant.restaurant_id", ondelete="CASCADE"), nullable=False
    )
    item_name_clean: Mapped[str] = mapped_column(String(300), nullable=False)
    item_name_raw: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    restaurant: Mapped[DimRestaurant] = relationship(back_populates="menu_items")


class EtlRunLog(Base):
    __tablename__ = "etl_run_logs"

    run_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    pipeline_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    source_name: Mapped[str] = mapped_column(String(64), nullable=False, default="baseline_csv")
    snapshot_batch_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rows_read: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_quarantined: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_upserted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class DataQualityResult(Base):
    __tablename__ = "data_quality_results"

    dq_result_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("etl_run_logs.run_id", ondelete="SET NULL"), nullable=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    dataset_scope: Mapped[str] = mapped_column(String(100), nullable=False)
    check_name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    failed_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    details_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)


class FactMenuSnapshot(Base):
    __tablename__ = "fact_menu_snapshot"
    __table_args__ = (
        UniqueConstraint("snapshot_batch_id", "row_fingerprint", name="uq_fact_snapshot_batch_fingerprint"),
    )

    snapshot_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("etl_run_logs.run_id", ondelete="SET NULL"), nullable=True)
    snapshot_batch_id: Mapped[str] = mapped_column(String(64), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_name: Mapped[str] = mapped_column(String(64), nullable=False, default="baseline_csv")
    row_fingerprint: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    restaurant_id: Mapped[int] = mapped_column(
        ForeignKey("dim_restaurant.restaurant_id", ondelete="RESTRICT"), nullable=False
    )
    menu_item_id: Mapped[int] = mapped_column(
        ForeignKey("dim_menu_item.menu_item_id", ondelete="RESTRICT"), nullable=False
    )
    location_id: Mapped[int] = mapped_column(ForeignKey("dim_location.location_id", ondelete="RESTRICT"), nullable=False)
    cuisine_id: Mapped[int | None] = mapped_column(ForeignKey("dim_cuisine.cuisine_id", ondelete="SET NULL"), nullable=True)
    price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    log_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_per_vote: Mapped[float | None] = mapped_column(Float, nullable=True)
    dining_rating: Mapped[float | None] = mapped_column(Numeric(4, 2), nullable=True)
    delivery_rating: Mapped[float | None] = mapped_column(Numeric(4, 2), nullable=True)
    average_rating: Mapped[float | None] = mapped_column(Numeric(4, 2), nullable=True)
    dining_votes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    delivery_votes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    votes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_votes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    best_seller_raw: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_bestseller: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    restaurant_popularity: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_highly_rated: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    is_expensive: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
