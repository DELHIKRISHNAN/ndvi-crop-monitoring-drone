"""
Telemetry Parser
================
Subscribes to MAVLink telemetry streams from the Pixhawk and exposes a
clean, typed Python object with the latest vehicle state.

Runs a background thread that continuously reads messages and updates
a thread-safe ``VehicleState`` snapshot.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

try:
    from pymavlink import mavutil  # type: ignore[import-untyped]

    _HAS_MAVLINK = True
except ImportError:
    _HAS_MAVLINK = False


# ---------------------------------------------------------------------------
# Vehicle state container
# ---------------------------------------------------------------------------


@dataclass
class GPSPosition:
    lat: float = 0.0  # degrees (WGS-84)
    lon: float = 0.0  # degrees
    alt_msl: float = 0.0  # metres above mean sea level
    alt_rel: float = 0.0  # metres above home position
    fix_type: int = 0  # 0=no fix, 2=2D, 3=3D, 4=DGPS, 5=RTK
    satellites: int = 0
    hdop: float = 99.99
    timestamp: float = 0.0


@dataclass
class Attitude:
    roll: float = 0.0  # radians
    pitch: float = 0.0
    yaw: float = 0.0
    rollspeed: float = 0.0
    pitchspeed: float = 0.0
    yawspeed: float = 0.0
    timestamp: float = 0.0


@dataclass
class BatteryState:
    voltage: float = 0.0  # volts
    current: float = 0.0  # amps
    remaining: int = -1  # percent (−1 = unknown)
    timestamp: float = 0.0


@dataclass
class VehicleState:
    """Thread-safe snapshot of the latest telemetry."""

    gps: GPSPosition = field(default_factory=GPSPosition)
    attitude: Attitude = field(default_factory=Attitude)
    battery: BatteryState = field(default_factory=BatteryState)
    armed: bool = False
    flight_mode: str = "UNKNOWN"
    heading: float = 0.0  # degrees 0–360
    groundspeed: float = 0.0  # m/s
    airspeed: float = 0.0  # m/s
    last_update: float = 0.0


# ---------------------------------------------------------------------------
# Telemetry listener
# ---------------------------------------------------------------------------


class TelemetryListener:
    """Background telemetry reader that populates a ``VehicleState``.

    Parameters
    ----------
    mavlink_client
        An already-connected ``MAVLinkClient`` instance.
    update_rate_hz : float
        How fast to poll for new messages (default 50 Hz).
    """

    def __init__(self, mavlink_client, *, update_rate_hz: float = 50.0):
        from flight.mavlink_client import MAVLinkClient

        self._client: MAVLinkClient = mavlink_client
        self._rate = 1.0 / update_rate_hz
        self._state = VehicleState()
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None

    @property
    def state(self) -> VehicleState:
        """Return a snapshot of the latest vehicle state (thread-safe read)."""
        with self._lock:
            return self._state

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(
            target=self._loop,
            daemon=True,
            name="telemetry-listener",
        )
        self._thread.start()
        logger.info("Telemetry listener started (%.0f Hz)", 1.0 / self._rate)

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
        logger.info("Telemetry listener stopped")

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def _loop(self) -> None:
        while self._running:
            msg = self._client.recv_match("", blocking=False, timeout=0.01)
            if msg is None:
                time.sleep(self._rate)
                continue
            self._dispatch(msg)

    def _dispatch(self, msg) -> None:
        msg_type = msg.get_type()
        now = time.time()

        with self._lock:
            if msg_type == "GLOBAL_POSITION_INT":
                self._state.gps.lat = msg.lat / 1e7
                self._state.gps.lon = msg.lon / 1e7
                self._state.gps.alt_msl = msg.alt / 1000.0
                self._state.gps.alt_rel = msg.relative_alt / 1000.0
                self._state.gps.timestamp = now
                self._state.heading = msg.hdg / 100.0

            elif msg_type == "GPS_RAW_INT":
                self._state.gps.fix_type = msg.fix_type
                self._state.gps.satellites = msg.satellites_visible
                self._state.gps.hdop = msg.eph / 100.0 if msg.eph != 65535 else 99.99

            elif msg_type == "ATTITUDE":
                self._state.attitude = Attitude(
                    roll=msg.roll,
                    pitch=msg.pitch,
                    yaw=msg.yaw,
                    rollspeed=msg.rollspeed,
                    pitchspeed=msg.pitchspeed,
                    yawspeed=msg.yawspeed,
                    timestamp=now,
                )

            elif msg_type == "SYS_STATUS":
                self._state.battery.voltage = msg.voltage_battery / 1000.0
                self._state.battery.current = msg.current_battery / 100.0
                self._state.battery.remaining = msg.battery_remaining
                self._state.battery.timestamp = now

            elif msg_type == "VFR_HUD":
                self._state.airspeed = msg.airspeed
                self._state.groundspeed = msg.groundspeed

            elif msg_type == "HEARTBEAT":
                self._state.armed = bool(msg.base_mode & 0x80)
                # Decode custom mode to string
                self._state.flight_mode = self._decode_mode(msg)

            self._state.last_update = now

    @staticmethod
    def _decode_mode(heartbeat_msg) -> str:
        """Best-effort decode of PX4 / ArduPilot flight mode."""
        try:
            return mavutil.mode_string_v10(heartbeat_msg)
        except Exception:
            return f"MODE_{heartbeat_msg.custom_mode}"

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.stop()
