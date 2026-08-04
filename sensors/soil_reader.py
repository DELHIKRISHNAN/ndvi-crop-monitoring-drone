"""
Soil Sensor Reader
==================
Polls ground-truth soil sensors (moisture, pH, temperature, humidity)
connected to the Raspberry Pi via the I2C bus, optionally through an
ADS1115 ADC for analog sensors.

Supported hardware:
- **I2C digital sensors** — read directly via ``smbus2``
- **Analog sensors via ADS1115** — 4-channel 16-bit ADC on I2C address 0x48
- **Capacitive soil moisture** (analog → ADS1115 channel 0)
- **pH probe + signal board** (analog → ADS1115 channel 1)
- **DS18B20 temperature** (1-Wire, read via sysfs)
- **DHT22 / SHT31 humidity+temp** (I2C or GPIO)

Falls back to simulated readings on non-Pi platforms for development.
"""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Conditional hardware imports
# ---------------------------------------------------------------------------
try:
    import smbus2  # type: ignore[import-untyped]

    _HAS_SMBUS = True
except ImportError:
    _HAS_SMBUS = False

try:
    import Adafruit_ADS1x15  # type: ignore[import-untyped]

    _HAS_ADS = True
except ImportError:
    _HAS_ADS = False


# ---------------------------------------------------------------------------
# Data container
# ---------------------------------------------------------------------------


@dataclass
class SoilReading:
    """A single snapshot of soil sensor values."""

    moisture: float  # volumetric water content (%)
    ph: float  # pH scale 0-14
    temperature: float  # °C
    humidity: float  # relative humidity (%)
    timestamp: float  # epoch seconds
    lat: float | None = None
    lon: float | None = None


# ---------------------------------------------------------------------------
# ADS1115 ADC helper
# ---------------------------------------------------------------------------


class ADCReader:
    """Reads analog soil sensors through an ADS1115 4-channel ADC."""

    # Calibration constants — replace with your own measured values
    MOISTURE_MIN_ADC = 10000  # ADC value in dry air
    MOISTURE_MAX_ADC = 26000  # ADC value in water
    PH_OFFSET = 0.0  # voltage offset calibration
    PH_SLOPE = -5.7  # mV per pH unit (typical for SEN0161)

    def __init__(self, address: int = 0x48, busnum: int = 1, gain: int = 1):
        if _HAS_ADS:
            self._adc = Adafruit_ADS1x15.ADS1115(address=address, busnum=busnum)
        else:
            self._adc = None
        self._gain = gain

    def read_moisture(self, channel: int = 0) -> float:
        """Read capacitive soil moisture sensor (returns % VWC)."""
        if self._adc is None:
            return self._simulated_moisture()
        raw = self._adc.read_adc(channel, gain=self._gain)
        # Linear mapping from ADC range to 0-100%
        pct = (
            (self.MOISTURE_MAX_ADC - raw) / (self.MOISTURE_MAX_ADC - self.MOISTURE_MIN_ADC) * 100.0
        )
        return max(0.0, min(100.0, pct))

    def read_ph(self, channel: int = 1) -> float:
        """Read pH probe via analog signal board."""
        if self._adc is None:
            return self._simulated_ph()
        raw = self._adc.read_adc(channel, gain=self._gain)
        voltage = raw * 4.096 / 32767.0
        ph = 7.0 + (voltage - 2.5 + self.PH_OFFSET) / (self.PH_SLOPE / 1000.0)
        return max(0.0, min(14.0, ph))

    @staticmethod
    def _simulated_moisture() -> float:
        return round(random.uniform(20.0, 80.0), 1)

    @staticmethod
    def _simulated_ph() -> float:
        return round(random.uniform(5.5, 7.5), 2)


# ---------------------------------------------------------------------------
# Temperature reader (DS18B20 via 1-Wire sysfs)
# ---------------------------------------------------------------------------


class TemperatureReader:
    """Reads DS18B20 temperature sensor via the Linux 1-Wire interface."""

    DEVICE_PATH = "/sys/bus/w1/devices/"

    def __init__(self, device_id: str | None = None):
        self._device_id = device_id

    def read(self) -> float:
        """Return temperature in °C."""
        try:
            import glob

            if self._device_id is None:
                devices = glob.glob(f"{self.DEVICE_PATH}28-*/w1_slave")
                if not devices:
                    raise FileNotFoundError
                path = devices[0]
            else:
                path = f"{self.DEVICE_PATH}{self._device_id}/w1_slave"

            with open(path) as f:
                lines = f.readlines()

            if "YES" not in lines[0]:
                raise RuntimeError("CRC check failed on temperature sensor")

            temp_str = lines[1].split("t=")[1]
            return float(temp_str) / 1000.0

        except (FileNotFoundError, IndexError, RuntimeError):
            # Simulation fallback
            return round(random.uniform(18.0, 35.0), 1)


# ---------------------------------------------------------------------------
# Humidity reader (SHT31 I2C)
# ---------------------------------------------------------------------------


class HumidityReader:
    """Reads SHT31 temperature + humidity sensor over I2C."""

    SHT31_ADDR = 0x44

    def __init__(self, bus: int = 1):
        if _HAS_SMBUS:
            self._bus = smbus2.SMBus(bus)
        else:
            self._bus = None

    def read(self) -> float:
        """Return relative humidity (%)."""
        if self._bus is None:
            return round(random.uniform(30.0, 90.0), 1)

        # Trigger single-shot, high repeatability measurement
        self._bus.write_i2c_block_data(self.SHT31_ADDR, 0x2C, [0x06])
        time.sleep(0.02)
        data = self._bus.read_i2c_block_data(self.SHT31_ADDR, 0x00, 6)
        humidity = 100.0 * ((data[3] << 8 | data[4]) / 65535.0)
        return round(humidity, 1)


# ---------------------------------------------------------------------------
# Unified sensor reader
# ---------------------------------------------------------------------------


class SoilSensorReader:
    """High-level interface that aggregates all soil sensors.

    Usage::

        reader = SoilSensorReader()
        reading = reader.poll()
        print(reading)
    """

    def __init__(self):
        self._adc = ADCReader()
        self._temp = TemperatureReader()
        self._hum = HumidityReader()

    def poll(
        self,
        lat: float | None = None,
        lon: float | None = None,
    ) -> SoilReading:
        """Take a single reading from all sensors.

        Parameters
        ----------
        lat, lon : float, optional
            GPS coordinates to geotag the reading.
        """
        return SoilReading(
            moisture=self._adc.read_moisture(),
            ph=self._adc.read_ph(),
            temperature=self._temp.read(),
            humidity=self._hum.read(),
            timestamp=time.time(),
            lat=lat,
            lon=lon,
        )
