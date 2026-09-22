import { useEffect, useState } from 'react'
import { Navigate, NavLink, Route, Routes, useParams } from 'react-router-dom'
import { api, subscribe } from './api.js'
import { fmtTime } from './format.js'
import Live from './pages/Live.jsx'
import Archive from './pages/Archive.jsx'
import MatchDetail from './pages/MatchDetail.jsx'
import Results from './pages/Results.jsx'
import useTitle from './useTitle.js'

// Secili lig tarayicida kalir. Uygulama genelinde TEK kaynak: gezinme
// cubugundaki lig sekmeleri, Arsiv'deki lig anahtari ve Istatistik sayfasi
// hep bu degeri okur/yazar.
const CHAMP_KEY = 'betodds.champ'

function storedChamp() {
  try {
    const v = localStorage.getItem(CHAMP_KEY)
    return v ? Number(v) : null
  } catch { return null }          // gizli sekme / depolama kapali
}

/** /lig/:champId -> o ligin canli sayfasi. Secimi ust bilesene bildirir. */
function LeaguePage({ pulse, onChamp, leagues }) {
  const { champId } = useParams()
  const champ = Number(champId)
  // Sekme basligi ligin KISA adi: gezinme sekmesinde ne yaziyorsa o.
  const league = leagues.find((l) => l.champ_id === champ) || null
  useTitle(league ? (league.short_name || league.name) : null)
  useEffect(() => { if (champ) onChamp(champ) }, [champ, onChamp])
  return <Live pulse={pulse} champ={champ} />
}

export default function App() {
  const [health, setHealth] = useState(null)
  const [stream, setStream] = useState('connecting')
  const [pulse, setPulse] = useState(0)
  const [leagues, setLeagues] = useState([])
  const [champ, setChamp] = useState(storedChamp)

  // Collector olaylari: her poll'da sayfalar kendini tazelesin diye
  // artan bir sayac yayinliyoruz.
  useEffect(() => subscribe(
    (ev) => { if (ev.type === 'poll' || ev.type === 'finished') setPulse((p) => p + 1) },
    setStream,
  ), [])

  // Her ligin KENDI sayfasi var. Ligler ayni oyunun cok farkli gol profilli
  // formatlari (5x5 Rush ~7 gol/mac, 3x3 ~13); tek bir karisik gorunum
  // hicbirini tarif etmiyordu.
  useEffect(() => {
    let alive = true
    api.leagues().then((ls) => {
      if (!alive) return
      setLeagues(ls)
      // Kayitli lig artik yoksa (silinmis / yeni kurulum) ilkine dus.
      setChamp((c) => (ls.some((l) => l.champ_id === c) ? c : ls[0]?.champ_id ?? null))
    }).catch(() => {})
    return () => { alive = false }
  }, [])

  useEffect(() => {
    if (champ == null) return
    try { localStorage.setItem(CHAMP_KEY, String(champ)) } catch { /* yok say */ }
  }, [champ])

  useEffect(() => {
    let alive = true
    const load = () => api.health().then((h) => alive && setHealth(h)).catch(() => {})
    load()
    const id = setInterval(load, 15000)
    return () => { alive = false; clearInterval(id) }
  }, [pulse])

  const c = health?.collector
  const collectorState = !c ? 'err' : c.last_error ? 'warn' : c.running ? 'ok' : 'warn'
  const collectorText = !c
    ? 'backend yok'
    : c.last_error
      ? `hata: ${c.last_error.slice(0, 40)}`
      : c.running
        ? `toplayıcı çalışıyor · son ${fmtTime(c.last_poll)}`
        : 'toplayıcı durdu'

  const league = leagues.find((l) => l.champ_id === champ) || null
  // Ligler yuklenmeden "/" hedefini bilemeyiz; kayitli lig varsa onu kullan.
  const home = champ != null ? `/lig/${champ}` : null

  return (
    <div className="app">
      <header className="top">
        <div className="brand">Bet<span>Odds</span></div>
        <nav className="tabs">
          {leagues.map((l) => (
            <NavLink key={l.champ_id} to={`/lig/${l.champ_id}`}
              className={({ isActive }) => isActive ? 'active' : ''}
              title={l.name}>
              {l.short_name || l.name || l.champ_id}
            </NavLink>
          ))}
          <NavLink to="/arsiv" className={({ isActive }) => isActive ? 'active' : ''}>Arşiv</NavLink>
          <NavLink to="/sonuclar" className={({ isActive }) => isActive ? 'active' : ''}>Sonuçlar</NavLink>
        </nav>

        <div className="status">
          {league && <span className="league-now">{league.name}</span>}
          <span><i className={`dot ${collectorState}`} />{collectorText}</span>
          <span>
            <i className={`dot ${stream === 'connected' ? 'ok' : 'warn'}`} />
            {stream === 'connected' ? 'canlı akış' : 'akış yeniden bağlanıyor'}
          </span>
          {health?.db && (
            <span>{health.db.matches} maç · {health.db.snapshots} arşiv · {health.db.ticks} tick</span>
          )}
        </div>
      </header>

      <Routes>
        <Route path="/" element={
          home ? <Navigate to={home} replace /> : <div className="empty">Yükleniyor…</div>} />
        <Route path="/lig/:champId"
          element={<LeaguePage pulse={pulse} onChamp={setChamp} leagues={leagues} />} />
        <Route path="/arsiv"
          element={<Archive champ={champ} leagues={leagues} onChamp={setChamp} />} />
        <Route path="/mac/:id" element={<MatchDetail pulse={pulse} />} />
        <Route path="/sonuclar"
          element={<Results champ={champ} leagues={leagues} onChamp={setChamp} />} />
        <Route path="*" element={<div className="empty">Sayfa bulunamadı.</div>} />
      </Routes>
    </div>
  )
}
