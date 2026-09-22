import { useEffect, useState } from 'react'
import { fmtOdd } from '../format.js'

/**
 * Mac kartinin altindaki taktik kutusu.
 *
 * Iki kural var, ikisi de KURAL; tahmin degil - modelin (predict.py) hicbir
 * bileseniyle karismaz, sadece elle konmus esikler:
 *
 *   KG VAR   Mac bitmesine <= KG_LAST_MINUTES kala taraflardan biri hala 0.
 *            Kalan sure start_ts + match_minutes'tan hesaplanir; ikisi de
 *            backend'den geliyor (match_minutes ligden lige degisiyor:
 *            5x5 Rush 11 dk, 3x3 10 dk).
 *
 *   BOL GOL  Mac ONCESI baslangic 1/2 orani ODDS_TACTICS'teki bir cifte
 *            esitse. Karsilastirma canli oranla DEGIL p1/p2 ile yapilir:
 *            mac ici oran skorla birlikte kayiyor, taktigin dayanagi acilis
 *            fiyati.
 */

// Kalan sure esigi (dakika) - "son 2 dakika".
const KG_LAST_MINUTES = 2

// Oran taktigi cifleri: [ev, deplasman, etiket]. Esitlik ODDS_EPS
// toleransiyla; oranlar ondalikli geldigi icin tam esitlik aramak
// 2.5200000000000005 gibi degerlerde kaciriyordu.
const ODDS_EPS = 0.005
const ODDS_TACTICS = [
  { p1: 2.52, p2: 1.94, label: 'ORAN TAKTİĞİ BOL GOL!' },
]

/** Maca kalan dakika; hesaplanamiyorsa null. */
function minutesLeft(m, now) {
  if (m.status !== 'live' || !m.start_ts || !m.match_minutes) return null
  const elapsed = (now - m.start_ts * 1000) / 60000
  return m.match_minutes - elapsed
}

export default function Tactics({ m }) {
  // Kalan sure saniye saniye akiyor: pano yalnizca poll'da (20 sn) yenileniyor
  // ve esik 2 dakika oldugu icin uyari 20 sn'ye kadar gec kalabilirdi.
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (m.status !== 'live') return undefined
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [m.status])

  const alerts = []

  const left = minutesLeft(m, now)
  const sh = m.score_home
  const sa = m.score_away
  if (left !== null && left <= KG_LAST_MINUTES && left > 0
      && sh !== null && sh !== undefined && sa !== null && sa !== undefined
      && (sh === 0 || sa === 0)) {
    alerts.push({
      key: 'kg',
      text: 'TAKTİK KG VAR OYNA',
      note: `${sh === 0 ? m.home : m.away} henüz gol atmadı · ${left.toFixed(1)} dk kaldı`,
    })
  }

  const hit = m.p1 != null && m.p2 != null && ODDS_TACTICS.find(
    (t) => Math.abs(m.p1 - t.p1) <= ODDS_EPS && Math.abs(m.p2 - t.p2) <= ODDS_EPS)
  if (hit) {
    alerts.push({
      key: 'odds',
      text: `${hit.label}(${fmtOdd(m.p1)}-${fmtOdd(m.p2)})`,
      note: 'maç öncesi başlangıç oranı bu taktiğin çiftiyle eşleşti',
    })
  }

  if (!alerts.length) return null
  return (
    <div className="tactics">
      <div className="tactics-head">Taktik</div>
      {alerts.map((a) => (
        <div className="tactic-alert" key={a.key}>
          <div className="tactic-text">{a.text}</div>
          <div className="tactic-note">{a.note}</div>
        </div>
      ))}
    </div>
  )
}
