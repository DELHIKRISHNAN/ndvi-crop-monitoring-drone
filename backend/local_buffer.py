"""
Local SQLite Buffer
===================
Stores NDVI readings and soil data in a local SQLite database on the
Raspberry Pi so that nothing is lost if the network drops mid-flight.

A background sync worker periodically pushes un-synced rows to the
remote FastAPI backend when connectivity is available.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent / "local_data.db"

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS readings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    lat         REAL NOT NULL,
    lon         REAL NOT NULL,
    alt         REAL DEFAULT 0,
    ndvi_mean   REAL,
    ndvi_min    REAL,
    ndvi_max    REAL,
    soil_moisture   REAL,
    soil_ph         REAL,
    soil_temperature REAL,
    soil_humidity    REAL,
    stress_zones    TEXT,           -- JSON-serialised list of zone dicts
    frame_path      TEXT,          -- path to saved false-color PNG
    timestamp       REAL NOT NULL,
    synced          INTEGER DEFAULT 0   -- 0=pending, 1=synced
);

CREATE INDEX IF NOT EXISTS idx_synced ON readings (synced);
CREATE INDEX IF NOT EXISTS idx_timestamp ON readings (timestamp);
"""


# ---------------------------------------------------------------------------
# Buffer database
# ---------------------------------------------------------------------------


class LocalBuffer:
    """SQLite buffer for offline data persistence.

    Thread-safe — uses a per-call connection pattern so it can be used
    from the capture thread, the sync thread, and the main thread
    simultaneously.
    """

    def __init__(self, db_path: Path | str = DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(_SCHEMA_SQL)
        logger.info("Local buffer DB ready at %s", self.db_path)

    # ------------------------------------------------------------------
    # Insert
    # ------------------------------------------------------------------

    def insert_reading(self, data: Dict[str, Any]) -> int:
        """Insert a new reading and return its row ID.

        Expected ``data`` keys::

            lat, lon, alt, ndvi_mean, ndvi_min, ndvi_max,
            soil_moisture, soil_ph, soil_temperature, soil_humidity,
            stress_zones (list[dict]), frame_path, timestamp
        """
        zones_json = json.dumps(data.get("stress_zones", []))

        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                """
                INSERT INTO readings
                    (lat, lon, alt, ndvi_mean, ndvi_min, ndvi_max,
                     soil_moisture, soil_ph, soil_temperature, soil_humidity,
                     stress_zones, frame_path, timestamp, synced)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    data.get("lat", 0),
                    data.get("lon", 0),
                    data.get("alt", 0),
                    data.get("ndvi_mean"),
                    data.get("ndvi_min"),
                    data.get("ndvi_max"),
                    data.get("soil_moisture"),
                    data.get("soil_ph"),
                    data.get("soil_temperature"),
                    data.get("soil_humidity"),
                    zones_json,
                    data.get("frame_path"),
                    data.get("timestamp", time.time()),
                ),
            )
            return cur.lastrowid  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get_unsynced(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return up to ``limit`` un-synced readings."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM readings WHERE synced = 0 ORDER BY timestamp LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]

    def mark_synced(self, row_ids: List[int]) -> None:
        """Mark the given rows as synced."""
        if not row_ids:
            return
        placeholders = ",".join("?" * len(row_ids))
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                f"UPDATE readings SET synced = 1 WHERE id IN ({placeholders})",
                row_ids,
            )

    def get_all_readings(self, limit: int = 500) -> List[Dict[str, Any]]:
        """Return recent readings (synced or not)."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM readings ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]

    @property
    def pending_count(self) -> int:
        with sqlite3.connect(self.db_path) as conn:
            return conn.execute("SELECT COUNT(*) FROM readings WHERE synced = 0").fetchone()[0]


# ---------------------------------------------------------------------------
# Background sync worker
# ---------------------------------------------------------------------------


class SyncWorker:
    """Pushes un-synced readings to the remote backend.

    Parameters
    ----------
    buffer : LocalBuffer
        Local SQLite buffer instance.
    backend_url : str
        Full URL to the POST /api/readings endpoint.
    interval : float
        Seconds between sync attempts.
    """

    def __init__(
        self,
        buffer: LocalBuffer,
        backend_url: str = "http://localhost:8000/api/readings",
        interval: float = 10.0,
    ):
        self._buffer = buffer
        self._url = backend_url
        self._interval = interval
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(
            target=self._loop,
            daemon=True,
            name="sync-worker",
        )
        self._thread.start()
        logger.info("Sync worker started (→ %s, every %.0fs)", self._url, self._interval)

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("Sync worker stopped")

    def _loop(self) -> None:
        import requests  # lazy import — not needed on all platforms

        while self._running:
            try:
                rows = self._buffer.get_unsynced()
                if rows:
                    resp = requests.post(
                        self._url,
                        json=rows,
                        timeout=10,
                        headers={"X-API-Key": self._get_api_key()},
                    )
                    if resp.status_code in (200, 201):
                        self._buffer.mark_synced([r["id"] for r in rows])
                        logger.info("Synced %d readings", len(rows))
                    else:
                        logger.warning("Sync failed: HTTP %d", resp.status_code)
            except Exception as exc:
                logger.debug("Sync attempt failed (offline?): %s", exc)

            time.sleep(self._interval)

    @staticmethod
    def _get_api_key() -> str:
        """Load the API key from environment or config."""
        import os

        return os.environ.get("NDVI_API_KEY", "dev-key-change-me")

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.stop()
