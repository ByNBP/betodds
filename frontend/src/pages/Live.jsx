import { useEffect, useState } from 'react'
import { api } from '../api.js'
import GoalExpectation from '../components/GoalExpectation.jsx'
import RecentFinished from '../components/RecentFinished.jsx'
import DayRates from '../components/DayRates.jsx'
import MatchHistory from '../components/MatchHistory.jsx'
import SimilarMatches from '../components/SimilarMatches.jsx'
import MatchCard from '../components/MatchCard.jsx'
import Tactics from '../components/Tactics.jsx'
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

  // Maclar alt alta: her satirda solda kart, saginda o eslesmenin gecmisi.
  // Yan yana dizilmis kartlarda gecmis kutusuna yer kalmiyordu.
  const rows = (list) => (
    <div className="match-rows">
      {list.map((m) => (
        <div className="match-row" key={m.event_id}>
          {/* Sol sutun: kart, altinda taktik kutusu. Kart <Link> oldugu icin
              taktik onun ICINE konamaz - tiklaninca mac detayina giderdi. */}
          <div className="match-left">
            <MatchCard m={m} />
            <Tactics m={m} />
          </div>
          <MatchHistory h2h={m.h2h} home={m.home} away={m.away} expect={m.expect} />
        </div>
      ))}
    </div>
  )

  // Mac bolumleri: once devam eden, sonra yaklasan.
  const sections = [
    live.length > 0 && { title: `Devam eden (${live.length})`, list: live },
    soon.length > 0 && { title: `Yaklaşan (${soon.length})`, list: soon },
  ].filter(Boolean)

  // Izgara (bkz. .live-layout): ust satirda solda son biten maclar, sagda son
  // gunun tutma oranlari; altta solda maclar, sagda gol beklentisi + benzer
  // maclar. Sag alt sutun ilk MAC KARTININ hizasindan baslar ve yapiskandir -
  // uzun listede asagi inerken ozet gorunur kalsin. Dar ekranda hepsi alt alta.
  return (
    <>
      <div className="live-layout">
        <div className="live-recent">
          <RecentFinished matches={data.recent_finished} />
        </div>

        <div className="live-rates">
          <DayRates champ={champ} refresh={data.recent_finished?.[0]?.event_id} />
        </div>

        {sections[0] && <h2 className="live-heading">{sections[0].title}</h2>}

        <div className="live-main">
          {sections.map((s, i) => (
            <div key={s.title}>
              {i > 0 && <h2 style={{ marginTop: 24 }}>{s.title}</h2>}
              {rows(s.list)}
            </div>
          ))}

          {data.live.length === 0 && (
            <div className="panel">
              <div className="empty">
                Şu anda izlenen maç yok.<br />
                <span className="muted">Toplayıcı çalışıyorsa yeni maçlar birkaç dakika içinde görünür.</span>
              </div>
            </div>
          )}
        </div>

        <aside className="live-side">
          <GoalExpectation matches={data.live} />
          <div>
            <SimilarMatches matches={data.live} />
          </div>
        </aside>
      </div>

      <div style={{ marginTop: 16 }}>
        <SeasonTrend trends={data.season_trends} />
      </div>

      {/* Sayac seridi sayfanin ALTINDA: bunlar durum bilgisi, gun icinde
          degismeyen sayilar. Ustte dururken ilk ekranin dortte birini
          yiyor ve asil is olan mac kartlarini asagi itiyordu. */}
      <footer className="page-footer">
        <StatTiles data={data} />
      </footer>
    </>
  )
}
