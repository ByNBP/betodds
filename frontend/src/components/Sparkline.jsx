import { Line, LineChart, ResponsiveContainer, Tooltip, YAxis } from 'recharts'
import { fmtOdd, fmtTime } from '../format.js'

/** Kart icindeki mini oran hareketi. Kimlik, kartin altindaki renkli
 *  noktalarla veriliyor; burada eksen ve efsane yok. */
export default function Sparkline({ ticks }) {
  if (!ticks || ticks.length < 2) return null
  const data = ticks.map((t) => ({
    label: fmtTime(t.taken_at), '1': t.o1, X: t.ox, '2': t.o2,
  }))
  return (
    <div className="spark">
      <ResponsiveContainer>
        <LineChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 4 }}>
          <YAxis hide domain={['dataMin', 'dataMax']} />
          <Tooltip
            contentStyle={{ background: '#1e2430', border: '1px solid #2a3140',
              borderRadius: 8, fontSize: 12, padding: '6px 10px' }}
            labelStyle={{ color: '#8d97a8' }}
            formatter={(v, n) => [fmtOdd(v), n]}
          />
          <Line type="stepAfter" dataKey="1" stroke="var(--series-1)" dot={false} strokeWidth={2} isAnimationActive={false} />
          <Line type="stepAfter" dataKey="X" stroke="var(--series-2)" dot={false} strokeWidth={2} isAnimationActive={false} />
          <Line type="stepAfter" dataKey="2" stroke="var(--series-3)" dot={false} strokeWidth={2} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
