import { useState, useEffect, useCallback } from 'react'
import NDVIMap from './components/NDVIMap'
import StatsRow from './components/StatsRow'
import AlertsPanel from './components/AlertsPanel'
import SoilChart from './components/SoilChart'

const API_BASE = '/api'

// Demo / fallback data (shown when backend is offline)
const DEMO_READINGS = [
  { id: 1, lat: 28.6139, lon: 77.2090, ndvi_mean: 0.72, soil_moisture: 42.5, soil_ph: 6.8, soil_temperature: 28.3, soil_humidity: 65.2, timestamp: new Date(Date.now() - 3600000).toISOString() },
  { id: 2, lat: 28.6145, lon: 77.2095, ndvi_mean: 0.35, soil_moisture: 28.1, soil_ph: 7.1, soil_temperature: 30.1, soil_humidity: 55.8, timestamp: new Date(Date.now() - 3000000).toISOString() },
  { id: 3, lat: 28.6150, lon: 77.2085, ndvi_mean: 0.12, soil_moisture: 15.3, soil_ph: 7.5, soil_temperature: 33.2, soil_humidity: 40.1, timestamp: new Date(Date.now() - 2400000).toISOString() },
  { id: 4, lat: 28.6135, lon: 77.2100, ndvi_mean: 0.68, soil_moisture: 50.2, soil_ph: 6.5, soil_temperature: 27.5, soil_humidity: 70.0, timestamp: new Date(Date.now() - 1800000).toISOString() },
  { id: 5, lat: 28.6142, lon: 77.2080, ndvi_mean: 0.85, soil_moisture: 55.8, soil_ph: 6.6, soil_temperature: 26.8, soil_humidity: 72.5, timestamp: new Date(Date.now() - 1200000).toISOString() },
  { id: 6, lat: 28.6148, lon: 77.2092, ndvi_mean: 0.45, soil_moisture: 32.4, soil_ph: 6.9, soil_temperature: 29.4, soil_humidity: 58.3, timestamp: new Date(Date.now() - 600000).toISOString() },
  { id: 7, lat: 28.6155, lon: 77.2078, ndvi_mean: 0.91, soil_moisture: 60.1, soil_ph: 6.4, soil_temperature: 25.9, soil_humidity: 75.0, timestamp: new Date(Date.now() - 300000).toISOString() },
  { id: 8, lat: 28.6130, lon: 77.2088, ndvi_mean: 0.18, soil_moisture: 12.8, soil_ph: 7.8, soil_temperature: 34.5, soil_humidity: 35.2, timestamp: new Date().toISOString() },
]

const DEMO_ALERTS = [
  { id: 1, severity: 'severe', message: 'Severe vegetation stress — NDVI 0.12 over 450px', lat: 28.6150, lon: 77.2085, ndvi_value: 0.12, acknowledged: false, created_at: new Date(Date.now() - 2400000).toISOString() },
  { id: 2, severity: 'severe', message: 'Bare soil detected — NDVI 0.18 at field edge', lat: 28.6130, lon: 77.2088, ndvi_value: 0.18, acknowledged: false, created_at: new Date().toISOString() },
  { id: 3, severity: 'moderate', message: 'Moderate stress zone — NDVI 0.35, moisture low', lat: 28.6145, lon: 77.2095, ndvi_value: 0.35, acknowledged: false, created_at: new Date(Date.now() - 3000000).toISOString() },
  { id: 4, severity: 'moderate', message: 'Declining vegetation health trend in sector B2', lat: 28.6148, lon: 77.2092, ndvi_value: 0.45, acknowledged: true, created_at: new Date(Date.now() - 600000).toISOString() },
]

function App() {
  const [readings, setReadings] = useState(DEMO_READINGS)
  const [alerts, setAlerts] = useState(DEMO_ALERTS)
  const [isOnline, setIsOnline] = useState(false)
  const [activeTab, setActiveTab] = useState('ndvi')

  const fetchData = useCallback(async () => {
    try {
      const [readingsRes, alertsRes] = await Promise.all([
        fetch(`${API_BASE}/readings?limit=100`),
        fetch(`${API_BASE}/alerts?limit=20`),
      ])
      if (readingsRes.ok) {
        const data = await readingsRes.json()
        if (data.length > 0) setReadings(data)
        setIsOnline(true)
      }
      if (alertsRes.ok) {
        const data = await alertsRes.json()
        if (data.length > 0) setAlerts(data)
      }
    } catch {
      setIsOnline(false)
    }
  }, [])

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 5000) // Poll every 5s
    return () => clearInterval(interval)
  }, [fetchData])

  // Compute summary stats
  const ndviValues = readings.filter(r => r.ndvi_mean != null).map(r => r.ndvi_mean)
  const avgNDVI = ndviValues.length > 0
    ? (ndviValues.reduce((a, b) => a + b, 0) / ndviValues.length).toFixed(3)
    : '—'

  const moistureValues = readings.filter(r => r.soil_moisture != null).map(r => r.soil_moisture)
  const avgMoisture = moistureValues.length > 0
    ? (moistureValues.reduce((a, b) => a + b, 0) / moistureValues.length).toFixed(1)
    : '—'

  const stressedCount = ndviValues.filter(v => v < 0.5).length
  const healthyPct = ndviValues.length > 0
    ? ((ndviValues.filter(v => v >= 0.5).length / ndviValues.length) * 100).toFixed(0)
    : '—'

  const unackedAlerts = alerts.filter(a => !a.acknowledged).length

  // Soil time-series data for charts
  const soilData = readings
    .filter(r => r.soil_moisture != null)
    .sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp))
    .map(r => ({
      time: new Date(r.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      moisture: r.soil_moisture,
      ph: r.soil_ph,
      temperature: r.soil_temperature,
      humidity: r.soil_humidity,
    }))

  return (
    <div className="dashboard">
      {/* Header */}
      <header className="dashboard-header">
        <div className="logo">
          <div className="logo-icon">🛸</div>
          <h1>NDVI Drone</h1>
        </div>
        <div className="header-status">
          <div className="status-pill">
            <span className={`status-dot ${isOnline ? 'online' : 'offline'}`} />
            {isOnline ? 'Live' : 'Demo Mode'}
          </div>
          <div className="status-pill">
            <span className="status-dot syncing" />
            {readings.length} readings
          </div>
        </div>
      </header>

      {/* Main content */}
      <main className="dashboard-content">
        {/* Stats row */}
        <StatsRow
          avgNDVI={avgNDVI}
          avgMoisture={avgMoisture}
          healthyPct={healthyPct}
          alertCount={unackedAlerts}
        />

        {/* Map */}
        <div className="map-panel">
          <div className="panel-header">
            <h2>Field Overview</h2>
            <div className="panel-tabs">
              <button
                className={`panel-tab ${activeTab === 'ndvi' ? 'active' : ''}`}
                onClick={() => setActiveTab('ndvi')}
              >
                NDVI Map
              </button>
              <button
                className={`panel-tab ${activeTab === 'soil' ? 'active' : ''}`}
                onClick={() => setActiveTab('soil')}
              >
                Soil Map
              </button>
            </div>
          </div>
          <div className="map-container">
            <NDVIMap readings={readings} activeTab={activeTab} />
          </div>
        </div>

        {/* Side panel */}
        <div className="side-panel">
          <AlertsPanel alerts={alerts} />
          <SoilChart data={soilData} />
        </div>
      </main>
    </div>
  )
}

export default App
