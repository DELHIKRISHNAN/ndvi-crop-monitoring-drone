"""
Main Orchestrator
=================
Top-level script that ties together the flight interface, camera capture,
NDVI processing, soil sensors, and local buffer into a single mission loop.

Intended to run on the Raspberry Pi 5 companion computer.

Usage:
    python -m main                     # flight mode (real hardware)
    python -m main --simulate          # desk testing with simulated data
    python -m main --ground-only       # soil sensors only (no flight)
"""

from __future__ import annotations

import argparse
import logging
import signal
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)-18s] %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")


def parse_args():
    parser = argparse.ArgumentParser(description="NDVI Drone — Mission Controller")
    parser.add_argument(
        "--simulate", action="store_true", help="Run with simulated sensors and camera"
    )
    parser.add_argument("--ground-only", action="store_true", help="Soil sensors only, no flight")
    parser.add_argument("--connection", default="/dev/ttyAMA0", help="MAVLink connection string")
    parser.add_argument("--baud", type=int, default=921600, help="MAVLink baud rate")
    parser.add_argument(
        "--capture-interval", type=float, default=2.0, help="Seconds between NDVI captures"
    )
    parser.add_argument(
        "--soil-interval", type=float, default=5.0, help="Seconds between soil sensor polls"
    )
    parser.add_argument(
        "--backend-url", default="http://localhost:8000/api/readings", help="Backend sync endpoint"
    )
    return parser.parse_args()


def run_mission(args):
    """Main mission loop."""
    from pathlib import Path

    from backend.local_buffer import LocalBuffer, SyncWorker
    from sensors.soil_reader import SoilSensorReader
    from vision.capture import DualCamera, save_frame_pair
    from vision.classify import detect_stress_zones
    from vision.false_color import apply_false_color
    from vision.ndvi import compute_ndvi, compute_ndvi_stats

    logger.info("=" * 60)
    logger.info("  NDVI DRONE — Mission Controller")
    logger.info("  Mode: %s", "SIMULATE" if args.simulate else "LIVE")
    logger.info("=" * 60)

    # --- Initialise components ---------------------------------------------
    buffer = LocalBuffer()
    sync_worker = SyncWorker(buffer, backend_url=args.backend_url)
    sync_worker.start()

    soil_reader = SoilSensorReader()

    # Camera (uses OpenCV fallback in simulate mode)
    camera = DualCamera(
        rgb_source=0 if args.simulate else 0,
        nir_source=1 if not args.simulate else 0,  # same cam in sim mode
    )

    # Flight interface (optional)
    telemetry_state = None
    if not args.ground_only:
        try:
            from flight.failsafe import FailsafeManager
            from flight.mavlink_client import MAVLinkClient
            from flight.telemetry import TelemetryListener

            mavlink = MAVLinkClient(
                connection_string=args.connection,
                baud=args.baud,
            )
            mavlink.connect()

            telemetry = TelemetryListener(mavlink)
            telemetry.start()

            failsafe = FailsafeManager(
                mavlink,
                telemetry,
                on_failsafe=lambda reason: logger.critical("FAILSAFE: %s", reason),
            )
            failsafe.start()

            telemetry_state = telemetry
            logger.info("Flight interface online")
        except Exception as e:
            logger.warning("Flight interface unavailable: %s", e)
            logger.info("Continuing without MAVLink telemetry")

    # --- Mission loop ------------------------------------------------------
    output_dir = Path("captured_frames")
    last_capture = 0.0
    last_soil = 0.0
    running = True

    def shutdown(sig, frame):
        nonlocal running
        logger.info("Shutdown signal received")
        running = False

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    logger.info("Mission loop started — press Ctrl+C to stop")

    try:
        while running:
            now = time.time()

            # Get GPS position from telemetry (if available)
            lat, lon, alt = 0.0, 0.0, 0.0
            if telemetry_state:
                state = telemetry_state.state
                lat, lon, alt = state.gps.lat, state.gps.lon, state.gps.alt_rel

            # --- NDVI capture cycle ----------------------------------------
            if now - last_capture >= args.capture_interval:
                last_capture = now
                try:
                    pair = camera.capture()
                    pair.lat, pair.lon, pair.alt = lat, lon, alt

                    # Process NDVI
                    ndvi = compute_ndvi(pair.nir, pair.rgb)
                    stats = compute_ndvi_stats(ndvi)
                    zones = detect_stress_zones(ndvi)

                    # Save false-color frame
                    apply_false_color(ndvi)
                    rgb_path, nir_path = save_frame_pair(pair, output_dir)

                    # Buffer the reading
                    buffer.insert_reading(
                        {
                            "lat": lat,
                            "lon": lon,
                            "alt": alt,
                            "ndvi_mean": stats["mean"],
                            "ndvi_min": stats["min"],
                            "ndvi_max": stats["max"],
                            "soil_moisture": None,
                            "soil_ph": None,
                            "stress_zones": [
                                {
                                    "label": z.label,
                                    "area_pixels": z.area_pixels,
                                    "mean_ndvi": z.mean_ndvi,
                                }
                                for z in zones
                            ],
                            "frame_path": str(rgb_path),
                            "timestamp": now,
                        }
                    )

                    logger.info(
                        "NDVI captured — mean=%.3f, zones=%d, pos=(%.6f, %.6f)",
                        stats["mean"],
                        len(zones),
                        lat,
                        lon,
                    )
                except Exception as e:
                    logger.error("Capture failed: %s", e)

            # --- Soil sensor cycle -----------------------------------------
            if now - last_soil >= args.soil_interval:
                last_soil = now
                try:
                    soil = soil_reader.poll(lat=lat, lon=lon)
                    buffer.insert_reading(
                        {
                            "lat": lat,
                            "lon": lon,
                            "alt": alt,
                            "soil_moisture": soil.moisture,
                            "soil_ph": soil.ph,
                            "soil_temperature": soil.temperature,
                            "soil_humidity": soil.humidity,
                            "timestamp": now,
                        }
                    )
                    logger.info(
                        "Soil — moisture=%.1f%%, pH=%.2f, temp=%.1f°C",
                        soil.moisture,
                        soil.ph,
                        soil.temperature,
                    )
                except Exception as e:
                    logger.error("Soil read failed: %s", e)

            time.sleep(0.1)  # avoid busy loop

    finally:
        logger.info("Shutting down…")
        camera.close()
        sync_worker.stop()
        if telemetry_state:
            telemetry_state.stop()
        logger.info("Mission complete — %d readings buffered", buffer.pending_count)


if __name__ == "__main__":
    args = parse_args()
    run_mission(args)
