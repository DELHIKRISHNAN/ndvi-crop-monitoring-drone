"""
Tests for backend/local_buffer.py
==================================
"""

import time
import pytest
from pathlib import Path

from backend.local_buffer import LocalBuffer


@pytest.fixture
def buffer(tmp_path):
    """Create a fresh LocalBuffer with a temp SQLite database."""
    db_path = tmp_path / "test_buffer.db"
    return LocalBuffer(db_path=db_path)


class TestLocalBuffer:
    def test_insert_and_retrieve(self, buffer):
        data = {
            "lat": 28.6139,
            "lon": 77.2090,
            "ndvi_mean": 0.65,
            "ndvi_min": 0.3,
            "ndvi_max": 0.9,
            "soil_moisture": 42.5,
            "soil_ph": 6.8,
            "timestamp": time.time(),
        }
        row_id = buffer.insert_reading(data)
        assert row_id >= 1

        all_readings = buffer.get_all_readings()
        assert len(all_readings) == 1
        assert all_readings[0]["lat"] == pytest.approx(28.6139)

    def test_unsynced_returns_pending(self, buffer):
        buffer.insert_reading({"lat": 0, "lon": 0, "timestamp": time.time()})
        buffer.insert_reading({"lat": 1, "lon": 1, "timestamp": time.time()})

        unsynced = buffer.get_unsynced()
        assert len(unsynced) == 2

    def test_mark_synced(self, buffer):
        buffer.insert_reading({"lat": 0, "lon": 0, "timestamp": time.time()})
        buffer.insert_reading({"lat": 1, "lon": 1, "timestamp": time.time()})

        unsynced = buffer.get_unsynced()
        buffer.mark_synced([r["id"] for r in unsynced])

        assert buffer.pending_count == 0
        assert len(buffer.get_unsynced()) == 0

    def test_pending_count(self, buffer):
        assert buffer.pending_count == 0
        buffer.insert_reading({"lat": 0, "lon": 0, "timestamp": time.time()})
        assert buffer.pending_count == 1

    def test_stress_zones_serialised_as_json(self, buffer):
        data = {
            "lat": 10.0,
            "lon": 20.0,
            "timestamp": time.time(),
            "stress_zones": [{"label": "severe_stress", "area_pixels": 500}],
        }
        buffer.insert_reading(data)
        rows = buffer.get_all_readings()
        assert '"severe_stress"' in rows[0]["stress_zones"]
