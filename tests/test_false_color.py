"""
Tests for vision/false_color.py
================================
"""

import numpy as np

from vision.false_color import (
    Palette,
    apply_false_color,
    create_legend,
    normalize_ndvi,
    overlay_ndvi_on_rgb,
)


class TestNormalizeNDVI:
    def test_minus_one_maps_to_zero(self):
        arr = np.array([-1.0], dtype=np.float32)
        result = normalize_ndvi(arr)
        assert result[0] == 0

    def test_plus_one_maps_to_255(self):
        arr = np.array([1.0], dtype=np.float32)
        result = normalize_ndvi(arr)
        assert result[0] == 255

    def test_zero_maps_to_midpoint(self):
        arr = np.array([0.0], dtype=np.float32)
        result = normalize_ndvi(arr)
        assert 125 <= result[0] <= 130  # ~127.5


class TestApplyFalseColor:
    def test_output_shape_and_dtype(self):
        ndvi = np.random.uniform(-1, 1, (50, 50)).astype(np.float32)
        colored = apply_false_color(ndvi)
        assert colored.shape == (50, 50, 3)
        assert colored.dtype == np.uint8

    def test_different_palettes_produce_different_outputs(self):
        ndvi = np.random.uniform(-1, 1, (20, 20)).astype(np.float32)
        jet = apply_false_color(ndvi, Palette.JET)
        inferno = apply_false_color(ndvi, Palette.INFERNO)
        assert not np.array_equal(jet, inferno)


class TestCreateLegend:
    def test_legend_dimensions(self):
        legend = create_legend(height=200, width=40)
        assert legend.shape[0] == 200
        assert legend.shape[1] == 40
        assert legend.shape[2] == 3


class TestOverlay:
    def test_overlay_blending(self):
        rgb = np.full((30, 30, 3), 128, dtype=np.uint8)
        ndvi = np.random.uniform(-1, 1, (30, 30)).astype(np.float32)
        blended = overlay_ndvi_on_rgb(rgb, ndvi, alpha=0.5)
        assert blended.shape == rgb.shape
        # With alpha=0.5, result should differ from pure RGB
        assert not np.array_equal(blended, rgb)
