"""
Tests for vision/ndvi.py
========================
NDVI is pure math — ideal for deterministic unit tests with known
input arrays and expected outputs.
"""

import numpy as np
import pytest

from vision.ndvi import compute_ndvi, compute_ndvi_stats


class TestComputeNDVI:
    """Test the core NDVI computation."""

    def test_uniform_nir_and_red_gives_zero(self):
        """When NIR == Red, NDVI should be ≈ 0."""
        nir = np.full((10, 10), 100, dtype=np.uint8)
        rgb = np.zeros((10, 10, 3), dtype=np.uint8)
        rgb[:, :, 2] = 100  # Red channel = 100

        ndvi = compute_ndvi(nir, rgb)
        assert ndvi.shape == (10, 10)
        np.testing.assert_allclose(ndvi, 0.0, atol=0.01)

    def test_high_nir_low_red_gives_positive(self):
        """High NIR, low Red → NDVI close to +1 (healthy vegetation)."""
        nir = np.full((10, 10), 200, dtype=np.uint8)
        rgb = np.zeros((10, 10, 3), dtype=np.uint8)
        rgb[:, :, 2] = 10  # low red

        ndvi = compute_ndvi(nir, rgb)
        assert np.all(ndvi > 0.8)

    def test_low_nir_high_red_gives_negative(self):
        """Low NIR, high Red → NDVI negative (water / artificial)."""
        nir = np.full((10, 10), 10, dtype=np.uint8)
        rgb = np.zeros((10, 10, 3), dtype=np.uint8)
        rgb[:, :, 2] = 200

        ndvi = compute_ndvi(nir, rgb)
        assert np.all(ndvi < -0.5)

    def test_output_clipped_to_range(self):
        """All output values must be in [-1, 1]."""
        nir = np.random.randint(0, 256, (50, 50), dtype=np.uint8)
        rgb = np.random.randint(0, 256, (50, 50, 3), dtype=np.uint8)

        ndvi = compute_ndvi(nir, rgb)
        assert ndvi.min() >= -1.0
        assert ndvi.max() <= 1.0

    def test_zero_inputs_no_crash(self):
        """All-zero frames should not raise (division by zero guard)."""
        nir = np.zeros((10, 10), dtype=np.uint8)
        rgb = np.zeros((10, 10, 3), dtype=np.uint8)

        ndvi = compute_ndvi(nir, rgb)
        assert ndvi.shape == (10, 10)
        assert np.isfinite(ndvi).all()

    def test_three_channel_nir_is_handled(self):
        """If NIR arrives as 3-channel BGR, it should be auto-converted."""
        nir_3ch = np.full((10, 10, 3), 180, dtype=np.uint8)
        rgb = np.zeros((10, 10, 3), dtype=np.uint8)
        rgb[:, :, 2] = 50

        ndvi = compute_ndvi(nir_3ch, rgb)
        assert ndvi.shape == (10, 10)
        assert np.all(ndvi > 0.4)


class TestNDVIStats:
    """Test the descriptive statistics helper."""

    def test_stats_keys_present(self):
        arr = np.random.uniform(-1, 1, (20, 20)).astype(np.float32)
        stats = compute_ndvi_stats(arr)
        for key in ("mean", "std", "min", "max", "median"):
            assert key in stats

    def test_stats_values_reasonable(self):
        arr = np.full((10, 10), 0.5, dtype=np.float32)
        stats = compute_ndvi_stats(arr)
        assert stats["mean"] == pytest.approx(0.5)
        assert stats["std"] == pytest.approx(0.0)
        assert stats["min"] == pytest.approx(0.5)
        assert stats["max"] == pytest.approx(0.5)
