import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from 'recharts'
import { useState } from 'react'

const METRICS = {
  moisture: { key: 'moisture', label: 'Moisture (%)', color: '#3b82f6', gradientId: 'gradMoisture' },
  ph: { key: 'ph', label: 'pH', color: '#c084fc', gradientId: 'gradPH' },
  temperature: { key: 'temperature', label: 'Temp (°C)', color: '#f97316', gradientId: 'gradTemp' },
  humidity: { key: 'humidity', label: 'Humidity (%)', color: '#22d3ee', gradientId: 'gradHumidity' },
}

function SoilChart({ data }) {
  const [activeMetric, setActiveMetric] = useState('moisture')
  const metric = METRICS[activeMetric]

  return (
    <div className="chart-panel">
      <div className="panel-header">
        <h2>Soil Analytics</h2>
        <div className="panel-tabs">
          {Object.entries(METRICS).map(([key, m]) => (
            <button
              key={key}
              className={`panel-tab ${activeMetric === key ? 'active' : ''}`}
              onClick={() => setActiveMetric(key)}
            >
              {m.label.split(' ')[0]}
            </button>
          ))}
        </div>
      </div>

      <div className="chart-container">
        {data.length === 0 ? (
          <div className="empty-state">
            <div className="empty-state-icon">📊</div>
            <p>No soil data available yet</p>
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
              <defs>
                <linearGradient id={metric.gradientId} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={metric.color} stopOpacity={0.3} />
                  <stop offset="95%" stopColor={metric.color} stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="time" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip
                contentStyle={{
                  background: '#111827',
                  border: '1px solid rgba(255,255,255,0.06)',
                  borderRadius: '10px',
                  fontSize: '12px',
                }}
              />
              <Area
                type="monotone"
                dataKey={metric.key}
                stroke={metric.color}
                strokeWidth={2}
                fill={`url(#${metric.gradientId})`}
                dot={{ r: 3, fill: metric.color, strokeWidth: 0 }}
                activeDot={{ r: 5, fill: metric.color, strokeWidth: 2, stroke: '#fff' }}
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  )
}

export default SoilChart
