import {
  CartesianGrid, Legend, Line, LineChart, ReferenceLine,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { fmtTime } from '../format.js'

/**
 * Oran hareketi. Mac oncesi ve canli faz ayrimini dikey cizgiyle gosterir;
 * gol anlarini (skor degisimi) isaretler.
 */
export default function OddsChart({ ticks }) {
  if (!ticks?.length) {
    return <div className="empty">Bu maç için oran hareketi kaydı yok.</div>
  }

  const data = ticks.map((t) => ({
    t: t.taken_at,
    label: fmtTime(t.taken_at),
    '1': t.o1, X: t.ox, '2': t.o2,
    score: t.score_home === null ? null : `${t.score_home}-${t.score_away}`,
    phase: t.phase,
  }))

  // Canli faza gecis ani
  const firstLive = data.find((d) => d.phase === 'live')
  // Skorun degistigi anlar = goller
  const goals = []
  for (let i = 1; i < data.length; i++) {
    if (data[i].score && data[i].score !== data[i - 1].score) goals.push(data[i])
  }

  return (
    <div style={{ width: '100%', height: 300 }}>
      <ResponsiveContainer>
        <LineChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: -12 }}>
          {/* hairline, duz - kesikli grid veri agirligi ekliyor */}
          <CartesianGrid stroke="var(--grid)" vertical={false} />
          <XAxis dataKey="label" stroke="#8d97a8" fontSize={11} minTickGap={28} />
          <YAxis stroke="#8d97a8" fontSize={11} domain={['auto', 'auto']} />
          <Tooltip
            contentStyle={{ background: '#1e2430', border: '1px solid #2a3140',
              borderRadius: 8, fontSize: 12 }}
            labelFormatter={(l, p) => {
              const s = p?.[0]?.payload?.score
              return s ? `${l} · skor ${s}` : l
            }}
          />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          {firstLive && (
            <ReferenceLine x={firstLive.label} stroke="#8d97a8"
              label={{ value: 'başladı', fill: '#8d97a8', fontSize: 11, position: 'top' }} />
          )}
          {goals.map((g) => (
            <ReferenceLine key={g.t} x={g.label} stroke="var(--series-3)" strokeOpacity={0.45}
              label={{ value: g.score, fill: '#8d97a8', fontSize: 10, position: 'top' }} />
          ))}
          <Line type="stepAfter" dataKey="1" stroke="var(--series-1)" dot={false} strokeWidth={2} />
          <Line type="stepAfter" dataKey="X" stroke="var(--series-2)" dot={false} strokeWidth={2} />
          <Line type="stepAfter" dataKey="2" stroke="var(--series-3)" dot={false} strokeWidth={2} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
