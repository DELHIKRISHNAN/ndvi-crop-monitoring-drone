"""
Tests for vision/classify.py
=============================
"""

import numpy as np
import pytest

from vision.classify import (
    NDVIThresholds,
    HealthLabel,
    classify_ndvi,
    detect_stress_zones,
)


class TestClassifyNDVI:
    def test_default_thresholds_healthy(self):
        """NDVI > 0.5 everywhere → all pixels classified as healthy (2)."""
        ndvi = np.full((20, 20), 0.7, dtype=np.float32)
        mask = classify_ndvi(ndvi)
        assert np.all(mask == 2)

    def test_default_thresholds_severe(self):
        """NDVI < 0.2 everywhere → all pixels classified as severe (0)."""
        ndvi = np.full((20, 20), 0.1, dtype=np.float32)
        mask = classify_ndvi(ndvi)
        assert np.all(mask == 0)

    def test_default_thresholds_moderate(self):
        """0.2 ≤ NDVI < 0.5 → moderate stress (1)."""
        ndvi = np.full((20, 20), 0.35, dtype=np.float32)
        mask = classify_ndvi(ndvi)
        assert np.all(mask == 1)

    def test_custom_thresholds(self):
        thresholds = NDVIThresholds(severe_stress=0.3, moderate_stress=0.6)
        ndvi = np.full((10, 10), 0.25, dtype=np.float32)
        mask = classify_ndvi(ndvi, thresholds)
        assert np.all(mask == 0)  # 0.25 < 0.3 → severe

    def test_mixed_zones(self):
        """Array with different regions should produce a mixed mask."""
        ndvi = np.zeros((30, 30), dtype=np.float32)
        ndvi[:10, :] = 0.1  # severe
        ndvi[10:20, :] = 0.3  # moderate
        ndvi[20:, :] = 0.8  # healthy
        mask = classify_ndvi(ndvi)
        assert np.all(mask[:10, :] == 0)
        assert np.all(mask[10:20, :] == 1)
        assert np.all(mask[20:, :] == 2)


class TestDetectStressZones:
    def test_no_stress_returns_empty(self):
        ndvi = np.full((50, 50), 0.8, dtype=np.float32)
        zones = detect_stress_zones(ndvi)
        assert zones == []

    def test_severe_blob_detected(self):
        """A large severe-stress region should be detected."""
        ndvi = np.full((100, 100), 0.7, dtype=np.float32)
        # Plant a 20x20 severe zone
        ndvi[40:60, 40:60] = 0.05
        zones = detect_stress_zones(ndvi, min_area_pixels=50)
        severe = [z for z in zones if z.label == HealthLabel.SEVERE]
        assert len(severe) >= 1
        assert severe[0].area_pixels > 50

    def test_small_blobs_filtered(self):
        """Blobs smaller than min_area_pixels should be ignored."""
        ndvi = np.full((100, 100), 0.7, dtype=np.float32)
        # Tiny 3x3 stress spot
        ndvi[50:53, 50:53] = 0.05
        zones = detect_stress_zones(ndvi, min_area_pixels=50)
        assert zones == []
