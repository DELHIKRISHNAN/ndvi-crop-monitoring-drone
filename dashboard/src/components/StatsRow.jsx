function StatsRow({ avgNDVI, avgMoisture, healthyPct, alertCount }) {
  return (
    <div className="stats-row">
      <div className="stat-card green">
        <span className="stat-label">Avg NDVI</span>
        <span className="stat-value green">{avgNDVI}</span>
        <span className="stat-change positive">
          ↑ Vegetation index
        </span>
      </div>

      <div className="stat-card blue">
        <span className="stat-label">Soil Moisture</span>
        <span className="stat-value blue">{avgMoisture}%</span>
        <span className="stat-change positive">
          Avg volumetric content
        </span>
      </div>

      <div className="stat-card green">
        <span className="stat-label">Healthy Coverage</span>
        <span className="stat-value green">{healthyPct}%</span>
        <span className="stat-change positive">
          NDVI ≥ 0.5
        </span>
      </div>

      <div className="stat-card red">
        <span className="stat-label">Active Alerts</span>
        <span className={`stat-value ${alertCount > 0 ? 'red' : 'green'}`}>
          {alertCount}
        </span>
        <span className={`stat-change ${alertCount > 0 ? 'negative' : 'positive'}`}>
          {alertCount > 0 ? '⚠ Needs attention' : '✓ All clear'}
        </span>
      </div>
    </div>
  )
}

export default StatsRow
