"""
Vegetation Stress Classifier
=============================
Classifies each pixel (or region) of an NDVI array into health categories
and detects contiguous stress zones suitable for alert generation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

import cv2
import numpy as np


# ---------------------------------------------------------------------------
# Default calibration thresholds (override per field / growing season)
# ---------------------------------------------------------------------------


@dataclass
class NDVIThresholds:
    """NDVI classification boundaries.

    These defaults are a reasonable starting point for broadacre crops in
    the vegetative growth stage.  **Calibrate** against ground-truth data
    from your actual test field before relying on alerts.
    """

    severe_stress: float = 0.2  # NDVI < this → bare soil / severe stress
    moderate_stress: float = 0.5  # severe_stress ≤ NDVI < this → moderate
    # NDVI ≥ moderate_stress → healthy


class HealthLabel:
    """String constants for classification labels."""

    SEVERE = "severe_stress"
    MODERATE = "moderate_stress"
    HEALTHY = "healthy"


# ---------------------------------------------------------------------------
# Per-pixel classification
# ---------------------------------------------------------------------------


def classify_ndvi(
    ndvi_array: np.ndarray,
    thresholds: NDVIThresholds | None = None,
) -> np.ndarray:
    """Classify each pixel into a health category.

    Returns an integer mask:
        0 = severe stress / bare soil
        1 = moderate stress
        2 = healthy vegetation
    """
    if thresholds is None:
        thresholds = NDVIThresholds()

    mask = np.full(ndvi_array.shape, 2, dtype=np.uint8)  # default healthy
    mask[ndvi_array < thresholds.moderate_stress] = 1
    mask[ndvi_array < thresholds.severe_stress] = 0
    return mask


# ---------------------------------------------------------------------------
# Stress-zone detection (contiguous regions)
# ---------------------------------------------------------------------------


@dataclass
class StressZone:
    """A single contiguous region of stressed vegetation."""

    label: str
    area_pixels: int
    centroid_x: float
    centroid_y: float
    bounding_box: tuple[int, int, int, int]  # (x, y, w, h)
    mean_ndvi: float


def detect_stress_zones(
    ndvi_array: np.ndarray,
    thresholds: NDVIThresholds | None = None,
    *,
    min_area_pixels: int = 100,
) -> List[StressZone]:
    """Find contiguous stress zones in an NDVI array.

    Parameters
    ----------
    ndvi_array : np.ndarray
        NDVI values in [−1, 1].
    thresholds : NDVIThresholds, optional
        Classification thresholds (uses defaults if not provided).
    min_area_pixels : int
        Ignore blobs smaller than this (noise filter).

    Returns
    -------
    list[StressZone]
        Detected zones sorted by area (largest first).
    """
    if thresholds is None:
        thresholds = NDVIThresholds()

    mask = classify_ndvi(ndvi_array, thresholds)
    zones: List[StressZone] = []

    for class_id, label in [(0, HealthLabel.SEVERE), (1, HealthLabel.MODERATE)]:
        binary = (mask == class_id).astype(np.uint8) * 255
        contours, _ = cv2.findContours(
            binary,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE,
        )
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < min_area_pixels:
                continue

            moments = cv2.moments(cnt)
            cx = moments["m10"] / (moments["m00"] + 1e-6)
            cy = moments["m01"] / (moments["m00"] + 1e-6)
            # cv2.boundingRect returns a sequence; unpacking ensures we get a tuple of 4 ints
            x, y, w, h = cv2.boundingRect(cnt)
            bbox = (x, y, w, h)

            # Mean NDVI inside the contour
            contour_mask = np.zeros(ndvi_array.shape, dtype=np.uint8)
            cv2.drawContours(contour_mask, [cnt], -1, (255,), -1)
            mean_val = cv2.mean(ndvi_array, mask=contour_mask)[0]

            zones.append(
                StressZone(
                    label=label,
                    area_pixels=int(area),
                    centroid_x=cx,
                    centroid_y=cy,
                    bounding_box=bbox,
                    mean_ndvi=mean_val,
                )
            )

    zones.sort(key=lambda z: z.area_pixels, reverse=True)
    return zones
