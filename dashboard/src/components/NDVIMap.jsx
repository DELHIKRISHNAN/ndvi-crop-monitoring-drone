import { MapContainer, TileLayer, CircleMarker, Tooltip } from 'react-leaflet'

function getNDVIColor(ndvi) {
  if (ndvi == null) return '#64748b'
  if (ndvi >= 0.7) return '#16a34a'  // dark green
  if (ndvi >= 0.5) return '#4ade80'  // green
  if (ndvi >= 0.3) return '#facc15'  // yellow
  if (ndvi >= 0.2) return '#f97316'  // orange
  return '#ef4444'                    // red
}

function getSoilColor(moisture) {
  if (moisture == null) return '#64748b'
  if (moisture >= 60) return '#3b82f6'  // blue (wet)
  if (moisture >= 40) return '#22d3ee'  // cyan
  if (moisture >= 25) return '#facc15'  // yellow
  return '#ef4444'                       // red (dry)
}

function NDVIMap({ readings, activeTab }) {
  // Center on the average position
  const validReadings = readings.filter(r => r.lat && r.lon)
  const center = validReadings.length > 0
    ? [
        validReadings.reduce((s, r) => s + r.lat, 0) / validReadings.length,
        validReadings.reduce((s, r) => s + r.lon, 0) / validReadings.length,
      ]
    : [28.6139, 77.2090]

  return (
    <div style={{ position: 'relative', height: '100%' }}>
      <MapContainer
        center={center}
        zoom={17}
        style={{ height: '100%', width: '100%' }}
        zoomControl={false}
      >
        <TileLayer
          attribution='&copy; <a href="https://carto.com">CARTO</a>'
          url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
        />

        {validReadings.map((reading) => {
          const isNDVI = activeTab === 'ndvi'
          const value = isNDVI ? reading.ndvi_mean : reading.soil_moisture
          const color = isNDVI
            ? getNDVIColor(reading.ndvi_mean)
            : getSoilColor(reading.soil_moisture)

          return (
            <CircleMarker
              key={reading.id}
              center={[reading.lat, reading.lon]}
              radius={12}
              pathOptions={{
                color: color,
                fillColor: color,
                fillOpacity: 0.7,
                weight: 2,
                opacity: 0.9,
              }}
            >
              <Tooltip direction="top" offset={[0, -10]}>
                <div style={{ fontFamily: 'Inter, sans-serif', fontSize: '12px' }}>
                  <strong>{isNDVI ? 'NDVI' : 'Moisture'}: </strong>
                  {value != null ? (isNDVI ? value.toFixed(3) : `${value.toFixed(1)}%`) : 'N/A'}
                  <br />
                  <span style={{ color: '#94a3b8' }}>
                    {reading.lat.toFixed(5)}, {reading.lon.toFixed(5)}
                  </span>
                </div>
              </Tooltip>
            </CircleMarker>
          )
        })}
      </MapContainer>

      {/* NDVI Legend */}
      <div className="ndvi-legend">
        <h4>{activeTab === 'ndvi' ? 'NDVI Scale' : 'Moisture Scale'}</h4>
        {activeTab === 'ndvi' ? (
          <>
            <div className="legend-item">
              <div className="legend-swatch" style={{ background: '#16a34a' }} />
              <span>≥ 0.7 Healthy</span>
            </div>
            <div className="legend-item">
              <div className="legend-swatch" style={{ background: '#4ade80' }} />
              <span>0.5 – 0.7 Good</span>
            </div>
            <div className="legend-item">
              <div className="legend-swatch" style={{ background: '#facc15' }} />
              <span>0.3 – 0.5 Moderate</span>
            </div>
            <div className="legend-item">
              <div className="legend-swatch" style={{ background: '#f97316' }} />
              <span>0.2 – 0.3 Stressed</span>
            </div>
            <div className="legend-item">
              <div className="legend-swatch" style={{ background: '#ef4444' }} />
              <span>&lt; 0.2 Severe</span>
            </div>
          </>
        ) : (
          <>
            <div className="legend-item">
              <div className="legend-swatch" style={{ background: '#3b82f6' }} />
              <span>≥ 60% Saturated</span>
            </div>
            <div className="legend-item">
              <div className="legend-swatch" style={{ background: '#22d3ee' }} />
              <span>40 – 60% Good</span>
            </div>
            <div className="legend-item">
              <div className="legend-swatch" style={{ background: '#facc15' }} />
              <span>25 – 40% Low</span>
            </div>
            <div className="legend-item">
              <div className="legend-swatch" style={{ background: '#ef4444' }} />
              <span>&lt; 25% Dry</span>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

export default NDVIMap
