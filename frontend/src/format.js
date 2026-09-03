// Ortak bicimlendiriciler.

export const fmtTime = (ts) =>
  ts ? new Date(ts * 1000).toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' }) : '—'

export const fmtDateTime = (ts) =>
  ts ? new Date(ts * 1000).toLocaleString('tr-TR', {
    day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
  }) : '—'

export const fmtOdd = (v) => (v === null || v === undefined ? '—' : Number(v).toFixed(2))

export const scoreText = (m) =>
  m.score_home === null || m.score_home === undefined ? 'vs' : `${m.score_home} - ${m.score_away}`

// Baslangica kalan/gecen sure. Kartlarda backend'in status_text'i yerine bunu
// kullaniyoruz: status_text son poll aninda dondugu icin toplayici durdugunda
// saatler sonra hala "3 dakika icinde basliyor" demeye devam eder.
const durText = (sec) => {
  const dk = Math.round(sec / 60)
  if (dk < 60) return `${dk} dakika`
  const sa = Math.floor(dk / 60)
  if (sa >= 24) return `${Math.floor(sa / 24)} gün`
  return dk % 60 ? `${sa} sa ${dk % 60} dk` : `${sa} saat`
}

export const startText = (m) => {
  if (m.status === 'live') return m.status_text || null   // canli dakika feed'den
  if (m.status !== 'scheduled' || !m.start_ts) return null
  const diff = m.start_ts - Date.now() / 1000
  if (diff > 0) return diff < 60 ? 'birazdan' : `${durText(diff)} içinde`
  return `${durText(-diff)} önce başlamalıydı`
}

export const STATUS_LABEL = {
  scheduled: 'Başlamadı',
  live: 'Canlı',
  finished: 'Bitti',
}

// Oranin ima ettigi olasilik (marj dahil) - oran hareketini yorumlamak icin.
export const impliedPct = (odd) => (odd ? (100 / odd).toFixed(1) + '%' : '—')
