import { useEffect, useState } from 'react'
import { api } from '../api.js'
import GoalDistribution from '../components/GoalDistribution.jsx'
import GoalExpectation from '../components/GoalExpectation.jsx'
import SimilarMatches from '../components/SimilarMatches.jsx'
import MatchCard from '../components/MatchCard.jsx'
import SeasonTrend from '../components/SeasonTrend.jsx'
import StatTiles from '../components/StatTiles.jsx'

export default function Live({ pulse, champ }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  // Pano TEK lige daralir: sayimlar, kapsama, mac basi gol, mac listesi ve
  // sezon trendi hep basliktaki secili lige ait.
  useEffect(() => {
    let alive = true
    api.dashboard(champ ?? undefined)
      .then((d) => alive && (setData(d), setError(null)))
      .catch((e) => alive && setError(e.message))
    return () => { alive = false }
  }, [pulse, champ])

  if (error) return <div className="error">Pano verisi alınamadı: {error}</div>
  if (!data) return <div className="empty">Yükleniyor…</div>

  const live = data.live.filter((m) => m.status === 'live')
  const soon = data.live.filter((m) => m.status === 'scheduled')

  return (
    <>
      <StatTiles data={data} />

      {live.length > 0 && (
        <>
          <h2>Devam eden ({live.length})</h2>
          <div className="cards">{live.map((m) => <MatchCard key={m.event_id} m={m} />)}</div>
        </>
      )}

      {soon.length > 0 && (
        <>
          <h2 style={{ marginTop: live.length ? 24 : 0 }}>Yaklaşan ({soon.length})</h2>
          <div className="cards">{soon.map((m) => <MatchCard key={m.event_id} m={m} />)}</div>
        </>
      )}

      {data.live.length === 0 && (
        <div className="panel">
          <div className="empty">
            Şu anda izlenen maç yok.<br />
            <span className="muted">Toplayıcı çalışıyorsa yeni maçlar birkaç dakika içinde görünür.</span>
          </div>
        </div>
      )}

      <div className="grid-2" style={{ marginTop: 20 }}>
        <GoalExpectation matches={data.live} />
        <GoalDistribution dist={data.goal_distribution} />
      </div>

      <div style={{ marginTop: 20 }}>
        <SimilarMatches matches={data.live} />
      </div>

      <div style={{ marginTop: 16 }}>
        <SeasonTrend trends={data.season_trends} />
      </div>
    </>
  )
}
