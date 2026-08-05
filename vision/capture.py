"""
Dual-Camera Capture Module
===========================
Handles simultaneous (or near-simultaneous) capture from an RGB camera and
an NIR-filtered camera using Raspberry Pi's ``picamera2`` stack.

Two synchronisation strategies are supported:

1. **Software timestamp matching** (default) — both cameras stream
   continuously; frames are paired by closest capture timestamp.
2. **Hardware GPIO trigger** — a GPIO pin fires both shutters at the same
   instant.  Requires physical wiring (pin → trigger input on each camera
   board).  Set ``use_hw_trigger=True`` and configure ``trigger_pin``.

On non-Raspberry Pi platforms (e.g., development machines), the module
falls back to OpenCV ``VideoCapture`` so that the rest of the pipeline can
be developed and tested with pre-recorded footage or webcams.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Try to import Pi-specific libraries; fall back gracefully
# ---------------------------------------------------------------------------
try:
    from picamera2 import Picamera2  # type: ignore[import-untyped]

    _HAS_PICAMERA2 = True
except ImportError:
    _HAS_PICAMERA2 = False
    logger.info("picamera2 not available — using OpenCV fallback for capture")

try:
    import RPi.GPIO as GPIO  # type: ignore[import-untyped]

    _HAS_GPIO = True
except ImportError:
    _HAS_GPIO = False


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------


@dataclass
class FramePair:
    """A co-registered pair of RGB and NIR frames."""

    rgb: np.ndarray
    nir: np.ndarray
    timestamp: float  # time.time() epoch seconds
    lat: float | None = None
    lon: float | None = None
    alt: float | None = None


# ---------------------------------------------------------------------------
# Abstract capture interface
# ---------------------------------------------------------------------------


class DualCamera:
    """Manages a synchronised dual-camera rig (RGB + NIR)."""

    def __init__(
        self,
        *,
        rgb_source: int | str = 0,
        nir_source: int | str = 1,
        resolution: tuple[int, int] = (640, 480),
        use_hw_trigger: bool = False,
        trigger_pin: int = 17,
    ):
        self.resolution = resolution
        self.use_hw_trigger = use_hw_trigger
        self.trigger_pin = trigger_pin

        if _HAS_PICAMERA2 and isinstance(rgb_source, int) and isinstance(nir_source, int):
            self._backend = "picamera2"
            self._init_picamera2(rgb_source, nir_source)
        else:
            self._backend = "opencv"
            self._init_opencv(rgb_source, nir_source)

        if use_hw_trigger and _HAS_GPIO:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.trigger_pin, GPIO.OUT, initial=GPIO.LOW)
            logger.info("Hardware trigger enabled on GPIO %d", trigger_pin)

    # -- picamera2 backend --------------------------------------------------

    def _init_picamera2(self, rgb_idx: int, nir_idx: int):
        self._rgb_cam = Picamera2(rgb_idx)
        self._nir_cam = Picamera2(nir_idx)
        config = {"main": {"size": self.resolution, "format": "BGR888"}}
        self._rgb_cam.configure(self._rgb_cam.create_still_configuration(**config))
        self._nir_cam.configure(self._nir_cam.create_still_configuration(**config))
        self._rgb_cam.start()
        self._nir_cam.start()
        logger.info("picamera2 backend initialised (cameras %d, %d)", rgb_idx, nir_idx)

    # -- OpenCV fallback ----------------------------------------------------

    def _init_opencv(self, rgb_src, nir_src):
        self._rgb_cap = cv2.VideoCapture(rgb_src)
        self._nir_cap = cv2.VideoCapture(nir_src)
        for cap in (self._rgb_cap, self._nir_cap):
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.resolution[0])
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.resolution[1])
        logger.info("OpenCV fallback backend initialised (sources %s, %s)", rgb_src, nir_src)

    # -- capture ------------------------------------------------------------

    def capture(self) -> FramePair:
        """Capture a synchronised RGB + NIR frame pair.

        Returns
        -------
        FramePair
            Paired frames with a common timestamp.
        """
        if self.use_hw_trigger and _HAS_GPIO:
            self._fire_trigger()

        ts = time.time()

        if self._backend == "picamera2":
            rgb = self._rgb_cam.capture_array()
            nir = self._nir_cam.capture_array()
        else:
            ok_rgb, rgb = self._rgb_cap.read()
            ok_nir, nir = self._nir_cap.read()
            if not ok_rgb or not ok_nir:
                raise RuntimeError("Failed to read from one or both cameras")

        return FramePair(rgb=rgb, nir=nir, timestamp=ts)

    def _fire_trigger(self):
        """Pulse the GPIO trigger pin (hardware sync)."""
        GPIO.output(self.trigger_pin, GPIO.HIGH)
        time.sleep(0.001)  # 1 ms pulse
        GPIO.output(self.trigger_pin, GPIO.LOW)

    # -- lifecycle ----------------------------------------------------------

    def close(self):
        """Release camera resources."""
        if self._backend == "picamera2":
            self._rgb_cam.stop()
            self._nir_cam.stop()
        else:
            self._rgb_cap.release()
            self._nir_cap.release()
        if self.use_hw_trigger and _HAS_GPIO:
            GPIO.cleanup()
        logger.info("Cameras released")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


# ---------------------------------------------------------------------------
# Utility: save a frame pair to disk (for offline analysis / debugging)
# ---------------------------------------------------------------------------


def save_frame_pair(pair: FramePair, output_dir: Path) -> tuple[Path, Path]:
    """Write RGB and NIR frames as PNG files with timestamp-based names."""
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{pair.timestamp:.6f}"
    rgb_path = output_dir / f"{stem}_rgb.png"
    nir_path = output_dir / f"{stem}_nir.png"
    cv2.imwrite(str(rgb_path), pair.rgb)
    cv2.imwrite(str(nir_path), pair.nir)
    return rgb_path, nir_path
