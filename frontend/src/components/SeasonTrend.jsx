import { useState } from 'react'
import {
  Area, AreaChart, CartesianGrid, ReferenceLine, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from 'recharts'

/**
 * Sezon basina mac basi gol - LIG BASINA ayri seri.
 *
 * Ligler ayni oyunun farkli formatlari ve gol profilleri taban tabana zit
 * (5x5 Rush ~7 gol/mac, 3x3 ~18). Tek eksende ust uste cizmek iki seriyi de
 * okunmaz yapardi; bu yuzden sekmeli: her seferinde tek lig, kendi olceginde.
 */
export default function SeasonTrend({ trends }) {
  const list = (trends || []).filter((t) => t.trend?.length)
  const [active, setActive] = useState(0)
  const [table, setTable] = useState(false)
  if (!list.length) return null

  const cur = list[Math.min(active, list.length - 1)]
  const trend = cur.trend
  const avg = trend.reduce((a, r) => a + r.avg_goals, 0) / trend.length
  const last = trend[trend.length - 1]

  // Domain'i string aritmetigiyle ('dataMax + 0.5') vermek 8.379999999999999
  // gibi bir tik uretiyor; uzun metin eksen alanindan tasip kuyrugu gorunuyordu.
  // Sinirlari yarim gol adimina yuvarlayip tikleri tek ondaliga bicimliyoruz.
  const values = trend.map((r) => r.avg_goals)
  const lo = Math.floor(Math.min(...values) * 2) / 2 - 0.5
  const hi = Math.ceil(Math.max(...values) * 2) / 2 + 0.5

  return (
    <div className="panel">
      <div className="chart-head">
        <h2>Sezon trendi — maç başı gol</h2>
        <button onClick={() => setTable((t) => !t)}>{table ? 'grafik' : 'tablo'}</button>
      </div>

      {list.length > 1 && (
        <div className="controls" style={{ marginTop: 4, marginBottom: 0 }}>
          {list.map((t, i) => (
            <button key={t.tourney_id} className={i === active ? 'primary' : ''}
              onClick={() => setActive(i)}>{t.name}</button>
          ))}
        </div>
      )}

      <div className="chart-sub">
        {trend.length} sezon · ortalama <strong>{avg.toFixed(2)}</strong> ·
        güncel sezon {last.iteration}: <strong>{last.avg_goals}</strong>
      </div>

      {table ? (
        <div className="scroll-x" style={{ marginTop: 12, maxHeight: 280 }}>
          <table>
            <thead><tr><th className="num">Sezon</th><th className="num">Maç</th>
              <th className="num">Maç başı gol</th></tr></thead>
            <tbody>
              {[...trend].reverse().map((r) => (
                <tr key={r.iteration}>
                  <td className="num">{r.iteration}</td>
                  <td className="num">{r.matches}</td>
                  <td className="num">{r.avg_goals}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div style={{ width: '100%', height: 220, marginTop: 8 }}>
          <ResponsiveContainer>
            <AreaChart data={trend} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
              <CartesianGrid stroke="var(--grid)" vertical={false} />
              <XAxis dataKey="iteration" stroke="#8d97a8" fontSize={11}
                tickLine={false} minTickGap={24} />
              <YAxis stroke="#8d97a8" fontSize={11} tickLine={false} width={38}
                domain={[lo, hi]} tickFormatter={(v) => v.toFixed(1)} />
              <Tooltip
                contentStyle={{ background: '#1e2430', border: '1px solid #2a3140',
                  borderRadius: 8, fontSize: 12 }}
                labelFormatter={(l) => `sezon ${l}`}
                formatter={(v, _n, p) => [`${v} gol/maç`, `${p.payload.matches} maç`]}
              />
              <ReferenceLine y={avg} stroke="#8d97a8" strokeOpacity={0.6}
                label={{ value: `ort. ${avg.toFixed(2)}`, fill: '#8d97a8',
                  fontSize: 11, position: 'insideTopLeft' }} />
              <Area type="monotone" dataKey="avg_goals" stroke="var(--seq-blue)"
                strokeWidth={2} fill="var(--seq-blue)" fillOpacity={0.1}
                isAnimationActive={false} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}
