# NDVI Drone 🌾🛸

**Precision-agriculture drone system for real-time vegetation health monitoring using NDVI (Normalized Difference Vegetation Index) analysis.**

Built around a Pixhawk Cube Orange flight controller, Raspberry Pi 5 companion computer, dual-camera rig (RGB + NIR), and ground-truth soil sensors — with a FastAPI backend and React dashboard for visualization.

---

## Gallery

### Bot Moving
<video src="img/VID-20251008-WA0006.mp4" controls="controls" width="100%">
  Your browser does not support the video tag. <a href="img/VID-20251008-WA0006.mp4">Download Video</a>
</video>

### Drone Images

**Drone Image**
![Drone Image](img/IMG_3868.HEIC)

**Drone Image (Work in Progress)**
![Drone Image (Not Fully Finished)](img/IMG_20251009_022551.jpg)

## System Architecture

```
[Pixhawk Cube Orange] ←MAVLink→ [Raspberry Pi 5]
                                       │
                  ┌────────────────────┼────────────────────┐
                  ▼                    ▼                    ▼
          [RGB+NIR Camera]      [Soil Sensors I2C]    [GPS via Pixhawk]
                  │                    │                    │
                  ▼                    ▼                    │
          [NDVI Pipeline]      [Sensor Reader]              │
                  │                    │                    │
                  └────────────┬───────┴────────────────────┘
                               ▼
                      [Local SQLite Buffer]
                               │
                               ▼ (sync when connected)
                      [FastAPI Backend + PostgreSQL]
                               │
                               ▼
                      [React Dashboard]
```

## Project Structure

```
ndvi-drone/
├── vision/                      # Camera & NDVI processing pipeline
│   ├── ndvi.py                  # Core NDVI computation (NIR−Red)/(NIR+Red)
│   ├── classify.py              # Vegetation stress classification
│   ├── false_color.py           # False-color rendering & overlays
│   └── capture.py               # Dual-camera capture (picamera2 + OpenCV)
│
├── flight/                      # Pixhawk interface layer
│   ├── mavlink_client.py        # MAVLink connection & heartbeat
│   ├── telemetry.py             # GPS/attitude/battery telemetry parser
│   └── failsafe.py              # Battery/GPS/geofence failsafe → RTL
│
├── sensors/                     # Ground-truth soil sensors
│   └── soil_reader.py           # Moisture, pH, temperature, humidity
│
├── backend/                     # Server-side services
│   ├── main.py                  # FastAPI application
│   ├── models.py                # SQLModel ORM + Pydantic schemas
│   ├── database.py              # Engine & session factory
│   └── local_buffer.py          # SQLite offline buffer + sync worker
│
├── ros2_ws/src/ndvi_drone_sim/  # ROS 2 + Gazebo simulation
│   ├── worlds/farmland.sdf      # Simulated farmland with stress zones
│   ├── launch/sim_launch.py     # Launch file (Gazebo + bridge + PID)
│   ├── config/pid_params.yaml   # Tuneable PID gains
│   └── ndvi_drone_sim/
│       └── pid_tuning_node.py   # PID attitude + altitude controller
│
├── dashboard/                   # React frontend (see dashboard/README.md)
├── tests/                       # pytest test suite
├── .github/workflows/test.yml   # CI pipeline
├── main.py                      # Mission orchestrator
├── requirements.txt             # Python dependencies
└── pyproject.toml               # Project metadata & tool config
```

## Quick Start

### 1. Clone & install

```bash
git clone https://github.com/yourusername/ndvi-drone.git
cd ndvi-drone
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### 2. Run tests

```bash
pytest
```

### 3. Start the backend API

```bash
cp .env.example .env
uvicorn backend.main:app --reload
```

API docs available at `http://localhost:8000/docs`

### 4. Run the mission controller (simulated mode)

```bash
python -m main --simulate
```

### 5. Run the ROS 2 simulation

```bash
cd ros2_ws
colcon build --packages-select ndvi_drone_sim
source install/setup.bash
ros2 launch ndvi_drone_sim sim_launch.py
```

## NDVI Algorithm

The core computation is straightforward:

```
NDVI = (NIR − Red) / (NIR + Red)
```

| NDVI Range | Classification |
|-----------|---------------|
| < 0.2 | Bare soil / severe stress |
| 0.2 – 0.5 | Moderate stress |
| > 0.5 | Healthy vegetation |

Thresholds are configurable per field and growing season — see `vision/classify.py`.

## Hardware

| Component | Model |
|-----------|-------|
| Flight controller | Pixhawk Cube Orange |
| Companion computer | Raspberry Pi 5 (8GB) |
| RGB camera | Raspberry Pi Camera Module 3 |
| NIR camera | Pi Camera + 850nm NIR-pass filter |
| Soil moisture | Capacitive sensor via ADS1115 ADC |
| Soil pH | SEN0161 analog pH probe |
| Temperature | DS18B20 (1-Wire) |
| Humidity | SHT31 (I2C) |
| Servo driver | PCA9685 (I2C) |

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/readings` | Push new NDVI + soil data |
| `GET` | `/api/readings` | List recent readings |
| `POST` | `/api/fields` | Create a monitored field |
| `GET` | `/api/fields/{id}/ndvi` | NDVI map data for a field |
| `GET` | `/api/fields/{id}/soil` | Soil stats time-series |
| `GET` | `/api/alerts` | Stressed-zone alerts |
| `PUT` | `/api/alerts/{id}/ack` | Acknowledge an alert |
| `GET` | `/api/health` | Health check |

All write endpoints require an `X-API-Key` header.

## Security

- API key authentication on all write endpoints
- Environment-based secrets management (`.env`)
- Input validation via Pydantic models
- CORS restricted to known dashboard origins

## License

MIT
