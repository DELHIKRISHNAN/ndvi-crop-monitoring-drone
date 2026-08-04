"""
NDVI Computation Engine
=======================
Computes the Normalized Difference Vegetation Index from co-registered
NIR and RGB frames captured by the dual-camera rig.

    NDVI = (NIR − Red) / (NIR + Red)

Values range from −1 (water / artificial surfaces) to +1 (dense, healthy
vegetation).  Results are returned as a float32 array clipped to [−1, 1].
"""

from __future__ import annotations

import cv2
import numpy as np


# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------


def compute_ndvi(
    nir_frame: np.ndarray,
    rgb_frame: np.ndarray,
    *,
    epsilon: float = 1e-6,
) -> np.ndarray:
    """Return a float32 NDVI array from co-registered NIR and RGB frames.

    Parameters
    ----------
    nir_frame : np.ndarray
        Near-infrared image (single-channel grayscale **or** 3-channel;
        if 3-channel, it is converted to grayscale internally).
    rgb_frame : np.ndarray
        Standard RGB image in BGR order (OpenCV default).
    epsilon : float
        Small constant added to the denominator to avoid division by zero.

    Returns
    -------
    np.ndarray
        2-D float32 array with values in [−1, 1].
    """
    # --- extract / convert channels ----------------------------------------
    if nir_frame.ndim == 3:
        nir = cv2.cvtColor(nir_frame, cv2.COLOR_BGR2GRAY).astype(np.float32)
    else:
        nir = nir_frame.astype(np.float32)

    # Red channel is index 2 in OpenCV's BGR layout
    red = rgb_frame[:, :, 2].astype(np.float32)

    # --- NDVI math ---------------------------------------------------------
    denominator = nir + red + epsilon
    ndvi = (nir - red) / denominator

    return np.clip(ndvi, -1.0, 1.0)


# ---------------------------------------------------------------------------
# Batch helpers
# ---------------------------------------------------------------------------


def compute_ndvi_stats(ndvi_array: np.ndarray) -> dict:
    """Return basic descriptive statistics for an NDVI array.

    Useful for per-frame metadata logging.
    """
    return {
        "mean": float(np.mean(ndvi_array)),
        "std": float(np.std(ndvi_array)),
        "min": float(np.min(ndvi_array)),
        "max": float(np.max(ndvi_array)),
        "median": float(np.median(ndvi_array)),
    }
