import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { fmtOdd, fmtTime } from '../format.js'
import GoalStats from './GoalStats.jsx'

/**
 * Secili macin mac oncesi 1/X/2 oranina yakin BITEN maclarin gol istatistigi.
 * Arsiv sayfasindaki oran filtresinin canli maca uygulanmis hali: "bu mac
 * neye benziyor" sorusunu gecmis veriden cevaplar.
 *
 * Benzerlik olcusu mac ONCESI oran (p1/px/p2); canli macin guncel orani mac
 * ici hareketi tasidigi icin karsilastirmaya uygun degil.
 */
export default function SimilarMatches({ matches }) {
  const usable = (matches || []).filter((m) => m.p1 && m.px && m.p2)
  const [eventId, setEventId] = useState(null)
  // Arsiv kucuk (skoru bilinen ~32 mac, oranlar 1.30-7.08): +/-0.25 cogu macta
  // bos donuyor. Varsayilan 0.50, kullanici daraltip genisletebilir.
  const [gap, setGap] = useState('0.50')
  const [stats, setStats] = useState(null)

  // Varsayilan odak: once canli mac, yoksa siradaki ilk mac. Secim kullanici
  // degistirene kadar korunur; liste degisince gecersiz secim duselir.
  const valid = usable.some((m) => m.event_id === eventId)
  const focus = valid
    ? usable.find((m) => m.event_id === eventId)
    : (usable.find((m) => m.status === 'live') || usable[0])

  const gapNum = Number(gap) > 0 ? gap : '0.50'
  const key = focus ? `${focus.event_id}:${gapNum}` : null

  useEffect(() => {
    if (!focus) { setStats(null); return }
    let alive = true
    api.matchStats({ o1: focus.p1, ox: focus.px, o2: focus.p2,
      gap: gapNum, status: 'finished' })
      .then((d) => alive && setStats(d))
      .catch(() => alive && setStats(null))
    return () => { alive = false }
  }, [key])                        // eslint-disable-line react-hooks/exhaustive-deps

  if (!focus) {
    return (
      <div className="panel">
        <div className="chart-head"><h2>Benzer maçların gol istatistiği</h2></div>
        <div className="empty">Maç öncesi oranı bilinen maç yok.</div>
      </div>
    )
  }

  return (
    <>
      <div className="controls odds-filter" style={{ marginBottom: 10 }}>
        <span className="muted">Benzer maçlar:</span>
        <select value={focus.event_id} style={{ width: 'auto' }}
          onChange={(e) => setEventId(Number(e.target.value))}>
          {usable.map((m) => (
            <option key={m.event_id} value={m.event_id}>
              {m.home} – {m.away} ({fmtTime(m.start_ts)})
            </option>
          ))}
        </select>
        <span className="muted">± </span>
        <input type="number" step="0.05" min="0.01" value={gap}
          onChange={(e) => setGap(e.target.value)} title="Tolerans (gap)" />
      </div>

      <GoalStats
        stats={stats}
        title="Benzer maçların gol istatistiği"
        subtitle={`${focus.home} – ${focus.away} · 1 ${fmtOdd(focus.p1)} `
          + `X ${fmtOdd(focus.px)} 2 ${fmtOdd(focus.p2)} · her orana ±${gapNum}`}
        empty="Bu orana yakın, skoru bilinen biten maç yok. Toleransı artırmayı deneyin."
      />
    </>
  )
}
