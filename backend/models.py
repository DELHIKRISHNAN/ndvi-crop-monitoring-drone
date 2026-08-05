"""
Database Models (SQLModel)
==========================
Defines the PostgreSQL / SQLite schema for the central backend database.
Uses SQLModel (Pydantic + SQLAlchemy fusion) for type-safe ORM access
that also serves as the FastAPI response schema.
"""

from datetime import datetime

from sqlmodel import Field, Relationship, SQLModel

# ---------------------------------------------------------------------------
# Core tables
# ---------------------------------------------------------------------------


class Field_area(SQLModel, table=True):
    """A monitored agricultural field / zone."""

    __tablename__ = "fields"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    description: str = ""
    lat_center: float = 0.0
    lon_center: float = 0.0
    area_hectares: float = 0.0
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    readings: list["Reading"] = Relationship(back_populates="field")


class Reading(SQLModel, table=True):
    """A single geotagged data point (NDVI + soil sensors)."""

    __tablename__ = "readings"

    id: int | None = Field(default=None, primary_key=True)
    field_id: int | None = Field(default=None, foreign_key="fields.id", index=True)

    # GPS
    lat: float
    lon: float
    alt: float = 0.0

    # NDVI stats
    ndvi_mean: float | None = None
    ndvi_min: float | None = None
    ndvi_max: float | None = None
    ndvi_std: float | None = None

    # Soil sensors
    soil_moisture: float | None = None
    soil_ph: float | None = None
    soil_temperature: float | None = None
    soil_humidity: float | None = None

    # Metadata
    stress_zones_json: str | None = None  # JSON blob
    frame_url: str | None = None  # URL / path to false-color image
    timestamp: datetime = Field(default_factory=datetime.utcnow, index=True)

    # Relationships
    field: Field_area | None = Relationship(back_populates="readings")


class Alert(SQLModel, table=True):
    """Auto-generated alert when stress zones are detected."""

    __tablename__ = "alerts"

    id: int | None = Field(default=None, primary_key=True)
    field_id: int | None = Field(default=None, foreign_key="fields.id", index=True)
    reading_id: int | None = Field(default=None, foreign_key="readings.id")

    severity: str = "moderate"  # "moderate" | "severe"
    message: str = ""
    lat: float = 0.0
    lon: float = 0.0
    ndvi_value: float | None = None
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
    ndvi_mean: float | None = None
    ndvi_min: float | None = None
    ndvi_max: float | None = None
    ndvi_std: float | None = None
    soil_moisture: float | None = None
    soil_ph: float | None = None
    soil_temperature: float | None = None
    soil_humidity: float | None = None
    stress_zones_json: str | None = None
    frame_url: str | None = None
    timestamp: datetime | None = None
    field_id: int | None = None


class ReadingResponse(SQLModel):
    """Schema for GET /api/readings responses."""

    id: int
    lat: float
    lon: float
    alt: float
    ndvi_mean: float | None
    ndvi_min: float | None
    ndvi_max: float | None
    soil_moisture: float | None
    soil_ph: float | None
    soil_temperature: float | None
    soil_humidity: float | None
    stress_zones_json: str | None
    frame_url: str | None
    timestamp: datetime
    field_id: int | None


class AlertResponse(SQLModel):
    """Schema for GET /api/alerts responses."""

    id: int
    severity: str
    message: str
    lat: float
    lon: float
    ndvi_value: float | None
    acknowledged: bool
    created_at: datetime
    field_id: int | None


class FieldCreate(SQLModel):
    """Schema for POST /api/fields."""

    name: str
    description: str = ""
    lat_center: float = 0.0
    lon_center: float = 0.0
    area_hectares: float = 0.0
