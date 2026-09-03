import { useState } from 'react'
import {
  Bar, BarChart, CartesianGrid, LabelList, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from 'recharts'

/**
 * Bahiscinin ima ettigi toplam gol dagilimi (market G=9939).
 * Is: siralanmis kategorilerde buyukluk karsilastirmasi -> cubuk, tek hue.
 */
export default function GoalDistribution({ dist }) {
  const [table, setTable] = useState(false)
  if (!dist) {
    return (
      <div className="panel">
        <h2>Toplam gol beklentisi</h2>
        <div className="empty">Maç öncesi arşivi olan bekleyen maç yok.</div>
      </div>
    )
  }

  const peak = dist.bins.reduce((a, b) => (b.prob > a.prob ? b : a), dist.bins[0])

  return (
    <div className="panel">
      <div className="chart-head">
        <h2>Toplam gol beklentisi</h2>
        <button onClick={() => setTable((t) => !t)}>
          {table ? 'grafik' : 'tablo'}
        </button>
      </div>
      <div className="chart-sub">
        {dist.home} – {dist.away} · maç öncesi oranlardan · en olası{' '}
        <strong>{peak.goals} gol</strong> · kitap marjı %{dist.margin}
      </div>

      {table ? (
        <div className="scroll-x" style={{ marginTop: 12 }}>
          <table>
            <thead><tr><th className="num">Gol</th><th className="num">Oran</th>
              <th className="num">Olasılık</th></tr></thead>
            <tbody>
              {dist.bins.map((b) => (
                <tr key={b.goals}>
                  <td className="num">{b.goals}</td>
                  <td className="num">{b.coef}</td>
                  <td className="num">%{b.prob}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div style={{ width: '100%', height: 260, marginTop: 8 }}>
          <ResponsiveContainer>
            <BarChart data={dist.bins} margin={{ top: 18, right: 8, bottom: 4, left: -14 }}>
              <CartesianGrid stroke="var(--grid)" vertical={false} />
              <XAxis dataKey="goals" stroke="#8d97a8" fontSize={11} tickLine={false}
                label={{ value: 'toplam gol', position: 'insideBottom', offset: -2,
                  fill: '#8d97a8', fontSize: 11 }} />
              <YAxis stroke="#8d97a8" fontSize={11} tickLine={false}
                tickFormatter={(v) => `%${v}`} />
              <Tooltip
                cursor={{ fill: 'rgba(255,255,255,0.04)' }}
                contentStyle={{ background: '#1e2430', border: '1px solid #2a3140',
                  borderRadius: 8, fontSize: 12 }}
                formatter={(v, _n, p) => [`%${v}  (oran ${p.payload.coef})`, 'olasılık']}
                labelFormatter={(l) => `${l} gol`}
              />
              {/* tek seri -> efsane yok; tepe noktasi dogrudan etiketli */}
              <Bar dataKey="prob" fill="var(--seq-blue)" maxBarSize={24}
                radius={[4, 4, 0, 0]} isAnimationActive={false}>
                <LabelList dataKey="prob" position="top" fontSize={11} fill="#8d97a8"
                  formatter={(v) => (v === peak.prob ? `%${v}` : '')} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}
