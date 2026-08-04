"""
Database Models (SQLModel)
==========================
Defines the PostgreSQL / SQLite schema for the central backend database.
Uses SQLModel (Pydantic + SQLAlchemy fusion) for type-safe ORM access
that also serves as the FastAPI response schema.
"""

from datetime import datetime
from typing import List, Optional

from sqlmodel import Field, SQLModel, Relationship


# ---------------------------------------------------------------------------
# Core tables
# ---------------------------------------------------------------------------

class Field_area(SQLModel, table=True):
    """A monitored agricultural field / zone."""
    __tablename__ = "fields"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    description: str = ""
    lat_center: float = 0.0
    lon_center: float = 0.0
    area_hectares: float = 0.0
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    readings: List["Reading"] = Relationship(back_populates="field")


class Reading(SQLModel, table=True):
    """A single geotagged data point (NDVI + soil sensors)."""
    __tablename__ = "readings"

    id: Optional[int] = Field(default=None, primary_key=True)
    field_id: Optional[int] = Field(default=None, foreign_key="fields.id", index=True)

    # GPS
    lat: float
    lon: float
    alt: float = 0.0

    # NDVI stats
    ndvi_mean: Optional[float] = None
    ndvi_min: Optional[float] = None
    ndvi_max: Optional[float] = None
    ndvi_std: Optional[float] = None

    # Soil sensors
    soil_moisture: Optional[float] = None
    soil_ph: Optional[float] = None
    soil_temperature: Optional[float] = None
    soil_humidity: Optional[float] = None

    # Metadata
    stress_zones_json: Optional[str] = None   # JSON blob
    frame_url: Optional[str] = None           # URL / path to false-color image
    timestamp: datetime = Field(default_factory=datetime.utcnow, index=True)

    # Relationships
    field: Optional[Field_area] = Relationship(back_populates="readings")


class Alert(SQLModel, table=True):
    """Auto-generated alert when stress zones are detected."""
    __tablename__ = "alerts"

    id: Optional[int] = Field(default=None, primary_key=True)
    field_id: Optional[int] = Field(default=None, foreign_key="fields.id", index=True)
    reading_id: Optional[int] = Field(default=None, foreign_key="readings.id")

    severity: str = "moderate"   # "moderate" | "severe"
    message: str = ""
    lat: float = 0.0
    lon: float = 0.0
    ndvi_value: Optional[float] = None
    acknowledged: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)


# ---------------------------------------------------------------------------
# Pydantic schemas (non-table models for request/response)
# ---------------------------------------------------------------------------

class ReadingCreate(SQLModel):
    """Schema for POST /api/readings."""
    lat: float
    lon: float
    alt: float = 0.0
    ndvi_mean: Optional[float] = None
    ndvi_min: Optional[float] = None
    ndvi_max: Optional[float] = None
    ndvi_std: Optional[float] = None
    soil_moisture: Optional[float] = None
    soil_ph: Optional[float] = None
    soil_temperature: Optional[float] = None
    soil_humidity: Optional[float] = None
    stress_zones_json: Optional[str] = None
    frame_url: Optional[str] = None
    timestamp: Optional[datetime] = None
    field_id: Optional[int] = None


class ReadingResponse(SQLModel):
    """Schema for GET /api/readings responses."""
    id: int
    lat: float
    lon: float
    alt: float
    ndvi_mean: Optional[float]
    ndvi_min: Optional[float]
    ndvi_max: Optional[float]
    soil_moisture: Optional[float]
    soil_ph: Optional[float]
    soil_temperature: Optional[float]
    soil_humidity: Optional[float]
    stress_zones_json: Optional[str]
    frame_url: Optional[str]
    timestamp: datetime
    field_id: Optional[int]


class AlertResponse(SQLModel):
    """Schema for GET /api/alerts responses."""
    id: int
    severity: str
    message: str
    lat: float
    lon: float
    ndvi_value: Optional[float]
    acknowledged: bool
    created_at: datetime
    field_id: Optional[int]


class FieldCreate(SQLModel):
    """Schema for POST /api/fields."""
    name: str
    description: str = ""
    lat_center: float = 0.0
    lon_center: float = 0.0
    area_hectares: float = 0.0
