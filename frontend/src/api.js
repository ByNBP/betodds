// Backend istemcisi + canli akis (SSE) yardimcilari.

async function get(path, params) {
  const qs = params
    ? '?' + new URLSearchParams(
        Object.entries(params).filter(([, v]) => v !== undefined && v !== '' && v !== null)
      ).toString()
    : ''
  const res = await fetch(`/api${path}${qs}`)
  if (!res.ok) {
    let detail = res.statusText
    try { detail = (await res.json()).detail || detail } catch { /* gövde JSON degil */ }
    throw new Error(detail)
  }
  return res.json()
}

export const api = {
  health: () => get('/health'),
  leagues: () => get('/leagues'),
  live: (champId) => get('/live', { champ_id: champId }),
  dashboard: (champId) => get('/dashboard', { champ_id: champId }),
  coverage: (champId) => get('/coverage', { champ_id: champId }),
  matches: (params) => get('/matches', params),
  results: (params) => get('/results', params),
  matchStats: (params) => get('/matches/stats', params),
  match: (id) => get(`/matches/${id}`),
  odds: (id) => get(`/matches/${id}/odds`),
  similar: (id, gap) => get(`/matches/${id}/similar`, { gap }),
  ticks: (id) => get(`/matches/${id}/ticks`),
  teamStats: (champId) => get('/stats/teams', { champ_id: champId }),
  seasons: (tourneyId, team) => get('/stats/seasons', { tourney_id: tourneyId, team }),
  seasonDetail: (tourneyId, it) => get(`/stats/seasons/${it}`, { tourney_id: tourneyId }),
}

// Collector olaylarini dinler; baglanti koparsa yeniden dener.
export function subscribe(onEvent, onStatus) {
  let es = null
  let closed = false
  let retry = null

  const open = () => {
    if (closed) return
    es = new EventSource('/api/stream')
    es.onopen = () => onStatus?.('connected')
    es.onmessage = (e) => {
      try { onEvent(JSON.parse(e.data)) } catch { /* keep-alive satiri */ }
    }
    es.onerror = () => {
      onStatus?.('reconnecting')
      es?.close()
      if (!closed) retry = setTimeout(open, 3000)
    }
  }
  open()

  return () => { closed = true; clearTimeout(retry); es?.close() }
}
