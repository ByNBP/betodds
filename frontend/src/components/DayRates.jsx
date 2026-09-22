import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { fmtDay } from '../format.js'
import HitRates from './HitRates.jsx'
import FavCounts from './FavCounts.jsx'

/**
 * Panonun sag ust kosesi: arsivin SON GUNUNDE beklenti ve ilk ust tutma
 * oranlari, favori/surpriz kazanan sayisi. Sonuclar sayfasi "Son gun" seciliyken gosterdigi sayilarla ayni
 * sorgu (api /results, tarih = son gun) - iki yerde farkli sayi cikmasin.
 *
 * `refresh`: yeni bir mac bittiginde degisen anahtar. Her poll'da (20 sn)
 * gunun tum maclarini yeniden hesaplamak bosuna olurdu.
 */
export default function DayRates({ champ, refresh }) {
  const [state, setState] = useState(null)

  useEffect(() => {
    let alive = true
    api.resultsSpan(champ ?? '')
      .then((s) => (s.last
        ? api.results({ champ_id: champ ?? '', date_from: s.last, date_to: s.last, limit: 1 })
          .then((d) => alive && setState({ day: s.last, rates: d.rates, total: d.total,
            favorite: d.favorite }))
        : alive && setState(null)))
      .catch(() => alive && setState(null))
    return () => { alive = false }
  }, [champ, refresh])

  if (!state) return null
  return (
    <div className="panel day-rates">
      <h3>Son gün · {fmtDay(state.day)} <span className="muted">· {state.total} maç</span></h3>
      <HitRates rates={state.rates} keys={['expect', 'over_first']} />
      <FavCounts fav={state.favorite} />
    </div>
  )
}
