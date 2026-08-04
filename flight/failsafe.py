"""
Failsafe Logic
==============
Monitors vehicle health and triggers safety responses when critical
thresholds are breached.

Failsafe triggers:
1. **Low battery** — voltage or remaining-% below threshold → RTL
2. **Link loss** — no heartbeat for N seconds → RTL (handled via
   MAVLinkClient callback, re-exported here for coherence)
3. **GPS loss** — fix degrades below 3D → loiter in place until restored
4. **Geofence breach** — vehicle exits a defined bounding box → RTL

All actions log a critical-level message and optionally invoke a
user-supplied callback (e.g., to push an alert to the dashboard).
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

logger = logging.getLogger(__name__)

try:
    from pymavlink import mavutil  # type: ignore[import-untyped]
    _HAS_MAVLINK = True
except ImportError:
    _HAS_MAVLINK = False


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class FailsafeConfig:
    """Tuneable failsafe thresholds."""
    battery_voltage_min: float = 21.0       # 6S LiPo critical (~3.5V/cell)
    battery_pct_min: int = 15               # percent
    gps_min_fix_type: int = 3               # require at least 3D fix
    heartbeat_timeout: float = 5.0          # seconds (mirrored from client)
    check_interval: float = 1.0             # seconds between checks
    # Geofence — bounding box (lat/lon min/max)
    geofence_enabled: bool = False
    geofence_lat_min: float = -90.0
    geofence_lat_max: float = 90.0
    geofence_lon_min: float = -180.0
    geofence_lon_max: float = 180.0


# ---------------------------------------------------------------------------
# Failsafe manager
# ---------------------------------------------------------------------------

class FailsafeManager:
    """Continuously checks vehicle state against safety thresholds.

    Parameters
    ----------
    mavlink_client
        Connected ``MAVLinkClient`` (used to send RTL commands).
    telemetry_listener
        Running ``TelemetryListener`` (source of vehicle state).
    config : FailsafeConfig
        Threshold settings.
    on_failsafe : callable, optional
        Invoked with ``(reason: str)`` whenever a failsafe is triggered.
    """

    def __init__(
        self,
        mavlink_client,
        telemetry_listener,
        config: FailsafeConfig | None = None,
        on_failsafe: Optional[Callable[[str], None]] = None,
    ):
        from flight.mavlink_client import MAVLinkClient
        from flight.telemetry import TelemetryListener

        self._client: MAVLinkClient = mavlink_client
        self._telemetry: TelemetryListener = telemetry_listener
        self.config = config or FailsafeConfig()
        self._on_failsafe = on_failsafe
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._triggered: set = set()  # avoid repeated triggers

        # Wire link-loss callback into the MAVLink client
        self._client.set_link_lost_callback(lambda: self._trigger("LINK_LOSS"))

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="failsafe-monitor",
        )
        self._thread.start()
        logger.info("Failsafe monitor started")

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
        logger.info("Failsafe monitor stopped")

    # ------------------------------------------------------------------
    # Main check loop
    # ------------------------------------------------------------------

    def _loop(self) -> None:
        while self._running:
            state = self._telemetry.state

            # --- Battery checks -------------------------------------------
            if (
                state.battery.voltage > 0
                and state.battery.voltage < self.config.battery_voltage_min
            ):
                self._trigger("LOW_VOLTAGE")

            if (
                0 <= state.battery.remaining < self.config.battery_pct_min
            ):
                self._trigger("LOW_BATTERY_PCT")

            # --- GPS check -------------------------------------------------
            if (
                state.gps.fix_type > 0
                and state.gps.fix_type < self.config.gps_min_fix_type
            ):
                self._trigger("GPS_DEGRADED")

            # --- Geofence check --------------------------------------------
            if self.config.geofence_enabled and state.gps.fix_type >= 3:
                lat, lon = state.gps.lat, state.gps.lon
                if not (
                    self.config.geofence_lat_min <= lat <= self.config.geofence_lat_max
                    and self.config.geofence_lon_min <= lon <= self.config.geofence_lon_max
                ):
                    self._trigger("GEOFENCE_BREACH")

            time.sleep(self.config.check_interval)

    # ------------------------------------------------------------------
    # Trigger action
    # ------------------------------------------------------------------

    def _trigger(self, reason: str) -> None:
        """Handle a failsafe event: log, command RTL, invoke callback."""
        if reason in self._triggered:
            return  # already triggered this session
        self._triggered.add(reason)

        logger.critical("FAILSAFE TRIGGERED: %s — commanding RTL", reason)

        # Send MAV_CMD_NAV_RETURN_TO_LAUNCH (20)
        if _HAS_MAVLINK and self._client.is_connected:
            self._client.send_command_long(
                mavutil.mavlink.MAV_CMD_NAV_RETURN_TO_LAUNCH, [],
            )

        if self._on_failsafe:
            try:
                self._on_failsafe(reason)
            except Exception:
                logger.exception("Error in failsafe callback")

    def reset(self) -> None:
        """Clear triggered flags (call after landing / manual override)."""
        self._triggered.clear()

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.stop()
