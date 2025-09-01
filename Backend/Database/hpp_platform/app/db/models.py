# app/db/models.py
from __future__ import annotations
from datetime import datetime, timezone
from app.db.base import Base
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import (
    String, Column, Integer, ForeignKey, Text, BigInteger, DateTime, Float,
    ForeignKey, UniqueConstraint, Index, CheckConstraint
)


class Base(DeclarativeBase):
    pass

class WeatherStation(Base):
    __tablename__ = "weather_stations"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # PK interne stable
    weather_station_code: Mapped[str] = mapped_column(String, unique=True, nullable=False)  # code réel (modifiable)
    weather_station_name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    plants = relationship("HydropowerPlant", back_populates="station")
    rainfalls = relationship(
    "Rainfall6Min",
    back_populates="station",
    cascade="all, delete-orphan",
    passive_deletes=True,          # <- important pour respecter ondelete=CASCADE
)

class HydropowerPlant(Base):
    __tablename__ = "hydropower_plants"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # PK interne stable
    hpp_code: Mapped[str] = mapped_column(String, unique=True, nullable=False)  # code réel centrale (modifiable)
    hpp_name: Mapped[str] = mapped_column(Text, nullable=False)
    weather_station_id: Mapped[int | None] = mapped_column(  # FK interne stable
        BigInteger, ForeignKey("weather_stations.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    station = relationship("WeatherStation", back_populates="plants")

class Rainfall6Min(Base):
    __tablename__ = "rainfall_6min"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    station_id = Column(Integer, ForeignKey("weather_stations.id", ondelete="CASCADE"), nullable=False)
    ts_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    rainfall_mm: Mapped[float] = mapped_column(Float, nullable=False)
    
    # ...
    __table_args__ = (
        UniqueConstraint("station_id", "ts_utc", name="uniq_station_ts"),
        Index("idx_rain_station_ts", "station_id", "ts_utc"),
        Index("idx_rain_ts", "ts_utc"),
        CheckConstraint("MOD((EXTRACT(EPOCH FROM ts_utc))::int, 360) = 0", name="chk_6min_aligned"),
        CheckConstraint("rainfall_mm >= 0", name="chk_rain_nonneg"),
    )
    station = relationship("WeatherStation", back_populates="rainfalls")