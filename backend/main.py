"""
FastAPI Backend — Main Application
====================================
RESTful API for the NDVI Drone system.

Endpoints:
    POST /api/readings          — drone pushes new NDVI + soil data
    GET  /api/readings          — list recent readings
    GET  /api/fields            — list monitored fields
    POST /api/fields            — create a new field
    GET  /api/fields/{id}/ndvi  — NDVI map data for a field
    GET  /api/fields/{id}/soil  — soil stats for a field
    GET  /api/alerts            — stressed-zone alerts
    PUT  /api/alerts/{id}/ack   — acknowledge an alert

Security:
    All write endpoints require an ``X-API-Key`` header.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session, select

from backend.database import engine, get_session, init_db
from backend.models import (
    Alert,
    AlertResponse,
    Field_area,
    FieldCreate,
    Reading,
    ReadingCreate,
    ReadingResponse,
)

# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

app = FastAPI(
    title="NDVI Drone API",
    description=(
        "Backend API for the precision-agriculture NDVI drone system. "
        "Receives geotagged NDVI + soil sensor readings from the Raspberry Pi "
        "companion computer and serves processed data to the React dashboard."
    ),
    version="0.1.0",
)

# CORS — allow the React dashboard in development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    init_db()


# ---------------------------------------------------------------------------
# Security dependency
# ---------------------------------------------------------------------------

API_KEY = os.environ.get("NDVI_API_KEY", "dev-key-change-me")


def verify_api_key(x_api_key: str = Header(...)) -> str:
    """Verify the API key on write endpoints."""
    if x_api_key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key",
        )
    return x_api_key


# ---------------------------------------------------------------------------
# Readings endpoints
# ---------------------------------------------------------------------------

@app.post(
    "/api/readings",
    response_model=ReadingResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["readings"],
)
def create_reading(
    payload: ReadingCreate,
    session: Session = Depends(get_session),
    _key: str = Depends(verify_api_key),
):
    """Accept a new geotagged reading from the drone."""
    reading = Reading(**payload.dict())
    if reading.timestamp is None:
        reading.timestamp = datetime.utcnow()
    session.add(reading)
    session.commit()
    session.refresh(reading)

    # Auto-generate alerts from stress zones
    _maybe_create_alerts(reading, session)

    return reading


@app.post(
    "/api/readings/batch",
    response_model=List[ReadingResponse],
    status_code=status.HTTP_201_CREATED,
    tags=["readings"],
)
def create_readings_batch(
    payloads: List[ReadingCreate],
    session: Session = Depends(get_session),
    _key: str = Depends(verify_api_key),
):
    """Accept a batch of readings (used by the sync worker)."""
    created = []
    for payload in payloads:
        reading = Reading(**payload.dict())
        if reading.timestamp is None:
            reading.timestamp = datetime.utcnow()
        session.add(reading)
        session.commit()
        session.refresh(reading)
        _maybe_create_alerts(reading, session)
        created.append(reading)
    return created


@app.get(
    "/api/readings",
    response_model=List[ReadingResponse],
    tags=["readings"],
)
def list_readings(
    limit: int = Query(100, ge=1, le=1000),
    field_id: Optional[int] = None,
    session: Session = Depends(get_session),
):
    """Return recent readings, optionally filtered by field."""
    stmt = select(Reading).order_by(Reading.timestamp.desc())  # type: ignore[attr-defined]
    if field_id is not None:
        stmt = stmt.where(Reading.field_id == field_id)
    stmt = stmt.limit(limit)
    return session.exec(stmt).all()


# ---------------------------------------------------------------------------
# Fields endpoints
# ---------------------------------------------------------------------------

@app.post(
    "/api/fields",
    response_model=Field_area,
    status_code=status.HTTP_201_CREATED,
    tags=["fields"],
)
def create_field(
    payload: FieldCreate,
    session: Session = Depends(get_session),
    _key: str = Depends(verify_api_key),
):
    field = Field_area(**payload.dict())
    session.add(field)
    session.commit()
    session.refresh(field)
    return field


@app.get("/api/fields", response_model=List[Field_area], tags=["fields"])
def list_fields(session: Session = Depends(get_session)):
    return session.exec(select(Field_area)).all()


@app.get("/api/fields/{field_id}/ndvi", tags=["fields"])
def get_field_ndvi(
    field_id: int,
    limit: int = Query(200, ge=1, le=2000),
    session: Session = Depends(get_session),
):
    """Return NDVI map data (lat, lon, ndvi_mean) for a field."""
    readings = session.exec(
        select(Reading)
        .where(Reading.field_id == field_id)
        .order_by(Reading.timestamp.desc())  # type: ignore[attr-defined]
        .limit(limit)
    ).all()
    return [
        {
            "lat": r.lat,
            "lon": r.lon,
            "ndvi": r.ndvi_mean,
            "timestamp": r.timestamp.isoformat() if r.timestamp else None,
        }
        for r in readings
    ]


@app.get("/api/fields/{field_id}/soil", tags=["fields"])
def get_field_soil(
    field_id: int,
    limit: int = Query(200, ge=1, le=2000),
    session: Session = Depends(get_session),
):
    """Return soil sensor time-series for a field."""
    readings = session.exec(
        select(Reading)
        .where(Reading.field_id == field_id)
        .order_by(Reading.timestamp.asc())  # type: ignore[attr-defined]
        .limit(limit)
    ).all()
    return [
        {
            "timestamp": r.timestamp.isoformat() if r.timestamp else None,
            "moisture": r.soil_moisture,
            "ph": r.soil_ph,
            "temperature": r.soil_temperature,
            "humidity": r.soil_humidity,
        }
        for r in readings
    ]


# ---------------------------------------------------------------------------
# Alerts endpoints
# ---------------------------------------------------------------------------

@app.get("/api/alerts", response_model=List[AlertResponse], tags=["alerts"])
def list_alerts(
    acknowledged: Optional[bool] = None,
    limit: int = Query(50, ge=1, le=500),
    session: Session = Depends(get_session),
):
    stmt = select(Alert).order_by(Alert.created_at.desc()).limit(limit)  # type: ignore[attr-defined]
    if acknowledged is not None:
        stmt = stmt.where(Alert.acknowledged == acknowledged)
    return session.exec(stmt).all()


@app.put("/api/alerts/{alert_id}/ack", tags=["alerts"])
def acknowledge_alert(
    alert_id: int,
    session: Session = Depends(get_session),
    _key: str = Depends(verify_api_key),
):
    alert = session.get(Alert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.acknowledged = True
    session.add(alert)
    session.commit()
    return {"status": "acknowledged"}


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/api/health", tags=["system"])
def health_check():
    return {"status": "ok", "service": "ndvi-drone-api"}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _maybe_create_alerts(reading: Reading, session: Session) -> None:
    """Parse stress_zones_json and auto-create alerts for severe zones."""
    if not reading.stress_zones_json:
        return
    try:
        zones = json.loads(reading.stress_zones_json)
    except (json.JSONDecodeError, TypeError):
        return

    for zone in zones:
        if zone.get("label") == "severe_stress":
            alert = Alert(
                field_id=reading.field_id,
                reading_id=reading.id,
                severity="severe",
                message=(
                    f"Severe vegetation stress detected — "
                    f"NDVI {zone.get('mean_ndvi', 'N/A'):.2f} "
                    f"over {zone.get('area_pixels', 0)} px"
                ),
                lat=reading.lat,
                lon=reading.lon,
                ndvi_value=zone.get("mean_ndvi"),
            )
            session.add(alert)
    session.commit()
