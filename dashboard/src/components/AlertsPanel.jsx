function AlertsPanel({ alerts }) {
  const sortedAlerts = [...alerts].sort(
    (a, b) => new Date(b.created_at) - new Date(a.created_at)
  )

  return (
    <div className="alerts-panel">
      <div className="panel-header">
        <h2>
          Alerts
          {alerts.filter(a => !a.acknowledged).length > 0 && (
            <span style={{
              marginLeft: '8px',
              fontSize: '0.7rem',
              background: 'rgba(239, 68, 68, 0.15)',
              color: '#f87171',
              padding: '2px 8px',
              borderRadius: '9999px',
              fontWeight: 600,
            }}>
              {alerts.filter(a => !a.acknowledged).length} new
            </span>
          )}
        </h2>
      </div>

      <div className="alert-list">
        {sortedAlerts.length === 0 ? (
          <div className="empty-state">
            <div className="empty-state-icon">✅</div>
            <p>No alerts — all zones healthy</p>
          </div>
        ) : (
          sortedAlerts.map((alert) => (
            <div
              key={alert.id}
              className="alert-item"
              style={{ opacity: alert.acknowledged ? 0.5 : 1 }}
            >
              <div className={`alert-severity ${alert.severity}`} />
              <div className="alert-content">
                <div className="alert-message">{alert.message}</div>
                <div className="alert-meta">
                  {new Date(alert.created_at).toLocaleString([], {
                    month: 'short',
                    day: 'numeric',
                    hour: '2-digit',
                    minute: '2-digit',
                  })}
                  {alert.ndvi_value != null && ` · NDVI ${alert.ndvi_value.toFixed(2)}`}
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}

export default AlertsPanel
