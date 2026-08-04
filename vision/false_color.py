"""
NDVI False-Color Renderer
=========================
Converts a float32 NDVI array into a visually interpretable BGR image
using OpenCV colormaps.  Supports multiple palette presets.
"""

from __future__ import annotations

from enum import Enum

import cv2
import numpy as np


class Palette(str, Enum):
    """Supported colormap presets."""

    JET = "jet"  # Classic rainbow (red-hot = high NDVI)
    RD_YL_GN = "rdylgn"  # Red → Yellow → Green (intuitive for crop health)
    INFERNO = "inferno"  # Perceptually uniform, good for papers


# Mapping from our palette names to OpenCV colormap constants
_CV_COLORMAPS = {
    Palette.JET: cv2.COLORMAP_JET,
    Palette.RD_YL_GN: cv2.COLORMAP_HSV,  # closest built-in approximation
    Palette.INFERNO: cv2.COLORMAP_INFERNO,
}


def normalize_ndvi(ndvi_array: np.ndarray) -> np.ndarray:
    """Map NDVI values from [−1, 1] to [0, 255] as uint8."""
    return ((ndvi_array + 1.0) / 2.0 * 255.0).astype(np.uint8)


def apply_false_color(
    ndvi_array: np.ndarray,
    palette: Palette = Palette.JET,
) -> np.ndarray:
    """Return a BGR false-color image from an NDVI float array.

    Parameters
    ----------
    ndvi_array : np.ndarray
        2-D float32 array with values in [−1, 1].
    palette : Palette
        Colormap to apply.

    Returns
    -------
    np.ndarray
        3-channel uint8 BGR image.
    """
    gray = normalize_ndvi(ndvi_array)
    cmap = _CV_COLORMAPS.get(palette, cv2.COLORMAP_JET)
    return cv2.applyColorMap(gray, cmap)


def create_legend(
    height: int = 300,
    width: int = 50,
    palette: Palette = Palette.JET,
) -> np.ndarray:
    """Create a vertical color-bar legend image.

    Useful for embedding next to the NDVI overlay on the dashboard.
    """
    gradient = np.linspace(255, 0, height, dtype=np.uint8).reshape(-1, 1)
    gradient = np.tile(gradient, (1, width))
    cmap = _CV_COLORMAPS.get(palette, cv2.COLORMAP_JET)
    legend = cv2.applyColorMap(gradient, cmap)

    # Add min/max text labels
    font = cv2.FONT_HERSHEY_SIMPLEX
    cv2.putText(legend, "+1.0", (2, 20), font, 0.4, (255, 255, 255), 1)
    cv2.putText(legend, " 0.0", (2, height // 2), font, 0.4, (255, 255, 255), 1)
    cv2.putText(legend, "-1.0", (2, height - 10), font, 0.4, (255, 255, 255), 1)

    return legend


def overlay_ndvi_on_rgb(
    rgb_frame: np.ndarray,
    ndvi_array: np.ndarray,
    *,
    alpha: float = 0.5,
    palette: Palette = Palette.JET,
) -> np.ndarray:
    """Blend a false-color NDVI overlay onto the original RGB frame.

    Parameters
    ----------
    rgb_frame : np.ndarray
        Original BGR image.
    ndvi_array : np.ndarray
        Corresponding NDVI array (same spatial dimensions).
    alpha : float
        Blending weight for the NDVI overlay (0 = only RGB, 1 = only NDVI).

    Returns
    -------
    np.ndarray
        Blended BGR image.
    """
    false_color = apply_false_color(ndvi_array, palette)
    if false_color.shape[:2] != rgb_frame.shape[:2]:
        false_color = cv2.resize(false_color, (rgb_frame.shape[1], rgb_frame.shape[0]))
    return cv2.addWeighted(false_color, alpha, rgb_frame, 1 - alpha, 0)
