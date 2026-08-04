"""
MAVLink Connection Client
=========================
Establishes and maintains a MAVLink connection to the Pixhawk flight
controller (Cube Orange) over UART or USB.

Uses ``pymavlink`` for low-level message handling.  The companion MAVSDK
alternative is documented but not used here because pymavlink gives finer
control over individual message types, which matters for custom telemetry
logging and the failsafe module.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy import — pymavlink is only available on the companion computer
# ---------------------------------------------------------------------------
try:
    from pymavlink import mavutil  # type: ignore[import-untyped]

    _HAS_MAVLINK = True
except ImportError:
    _HAS_MAVLINK = False
    logger.warning("pymavlink not installed — MAVLink client will run in stub mode")


class MAVLinkClient:
    """Persistent MAVLink connection with automatic heartbeat monitoring.

    Parameters
    ----------
    connection_string : str
        pymavlink connection URI.  Examples:
        - ``/dev/ttyAMA0`` (UART on Pi)
        - ``udp:127.0.0.1:14550`` (SITL / simulation)
        - ``tcp:192.168.1.10:5760`` (network bridge)
    baud : int
        Serial baud rate (ignored for UDP/TCP connections).
    heartbeat_timeout : float
        Seconds without a heartbeat before declaring link lost.
    source_system : int
        MAVLink system ID for this companion computer.
    """

    def __init__(
        self,
        connection_string: str = "/dev/ttyAMA0",
        baud: int = 921600,
        heartbeat_timeout: float = 5.0,
        source_system: int = 255,
    ):
        self.connection_string = connection_string
        self.baud = baud
        self.heartbeat_timeout = heartbeat_timeout
        self.source_system = source_system

        self._conn = None
        self._running = False
        self._heartbeat_thread: threading.Thread | None = None
        self._last_heartbeat: float = 0.0
        self._on_link_lost: Callable | None = None

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Open the MAVLink connection and start heartbeat monitoring."""
        if not _HAS_MAVLINK:
            logger.warning("Stub mode — no real MAVLink connection")
            return

        logger.info("Connecting to Pixhawk at %s (baud=%d)", self.connection_string, self.baud)
        self._conn = mavutil.mavlink_connection(
            self.connection_string,
            baud=self.baud,
            source_system=self.source_system,
        )
        # Wait for the first heartbeat to confirm link
        self._conn.wait_heartbeat(timeout=10)
        self._last_heartbeat = time.time()
        logger.info(
            "Heartbeat received — system %d, component %d",
            self._conn.target_system,
            self._conn.target_component,
        )

        # Start background heartbeat sender + monitor
        self._running = True
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            daemon=True,
            name="mavlink-heartbeat",
        )
        self._heartbeat_thread.start()

    def disconnect(self) -> None:
        """Gracefully close the connection."""
        self._running = False
        if self._heartbeat_thread:
            self._heartbeat_thread.join(timeout=3)
        if self._conn:
            self._conn.close()
            logger.info("MAVLink connection closed")

    # ------------------------------------------------------------------
    # Message I/O
    # ------------------------------------------------------------------

    def recv_match(self, msg_type: str, *, blocking: bool = True, timeout: float = 2.0):
        """Receive a specific MAVLink message type.

        Returns None if not available (non-blocking) or timeout expires.
        """
        if self._conn is None:
            return None
        return self._conn.recv_match(type=msg_type, blocking=blocking, timeout=timeout)

    def send_command_long(self, command: int, params: list) -> None:
        """Send a COMMAND_LONG to the flight controller.

        ``params`` should be a list of up to 7 float values.
        """
        if self._conn is None:
            return
        padded = (params + [0] * 7)[:7]
        self._conn.mav.command_long_send(
            self._conn.target_system,
            self._conn.target_component,
            command,
            0,  # confirmation
            *padded,
        )

    # ------------------------------------------------------------------
    # Heartbeat management
    # ------------------------------------------------------------------

    def set_link_lost_callback(self, callback: Callable) -> None:
        """Register a callback invoked when the heartbeat link is lost."""
        self._on_link_lost = callback

    def _heartbeat_loop(self) -> None:
        """Background thread: send heartbeats and monitor link health."""
        while self._running:
            # Send our own heartbeat to the Pixhawk
            if self._conn:
                self._conn.mav.heartbeat_send(
                    mavutil.mavlink.MAV_TYPE_ONBOARD_CONTROLLER,
                    mavutil.mavlink.MAV_AUTOPILOT_INVALID,
                    0,
                    0,
                    0,
                )

            # Check for incoming heartbeat
            msg = self.recv_match("HEARTBEAT", blocking=False, timeout=0.5)
            if msg:
                self._last_heartbeat = time.time()

            # Link-loss detection
            elapsed = time.time() - self._last_heartbeat
            if elapsed > self.heartbeat_timeout:
                logger.critical("Heartbeat lost (%.1fs since last)", elapsed)
                if self._on_link_lost:
                    self._on_link_lost()

            time.sleep(1.0)

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *exc):
        self.disconnect()

    @property
    def is_connected(self) -> bool:
        return self._conn is not None and self._running
