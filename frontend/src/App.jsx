import { useEffect, useState } from 'react'
import { Navigate, NavLink, Route, Routes, useParams } from 'react-router-dom'
import { api, subscribe } from './api.js'
import { fmtDateTime, fmtTime } from './format.js'
import Live from './pages/Live.jsx'
import Archive from './pages/Archive.jsx'
import MatchDetail from './pages/MatchDetail.jsx'
import Results from './pages/Results.jsx'
import useTitle from './useTitle.js'

// Secili lig tarayicida kalir. Uygulama genelinde TEK kaynak: gezinme
// cubugundaki lig sekmeleri, Arsiv'deki lig anahtari ve Istatistik sayfasi
// hep bu degeri okur/yazar.
const CHAMP_KEY = 'betodds.champ'

const PAGES = {
  sonuclar: { to: '/sonuclar', label: 'Sonuçlar' },
  arsiv: { to: '/arsiv', label: 'Arşiv' },
}
// 2986291 = FC 5x5 Superlig, 2860561 = 3x3 Konferans (data/leagues.json).
// Son eleman Arsiv olmali: listede olmayan ligler onun onune eklenir.
const MENU_ORDER = [2986291, 'sonuclar', 2860561, 'arsiv']

function storedChamp() {
  try {
    const v = localStorage.getItem(CHAMP_KEY)
    return v ? Number(v) : null
  } catch { return null }          // gizli sekme / depolama kapali
}

/** Sezon rozetinin ipucu: ne zaman basladi, kac macini gorduk. */
function seasonTitle(s) {
  const of = s.season_matches ? ` / ${s.season_matches}` : ''
  return `başlangıç ${fmtDateTime(s.since)} · arşivde ${s.matches}${of} maç`
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
  // pulse'ta yeniden cekilir: basliktaki guncel sezon numarasi sayfa acik
  // dururken de degisiyor (sezon 1-2 gunde bitiyor).
  useEffect(() => {
    let alive = true
    api.leagues().then((ls) => {
      if (!alive) return
      setLeagues(ls)
      // Kayitli lig artik yoksa (silinmis / yeni kurulum) ilkine dus.
      setChamp((c) => (ls.some((l) => l.champ_id === c) ? c : ls[0]?.champ_id ?? null))
    }).catch(() => {})
    return () => { alive = false }
  }, [pulse])

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

  // Ust menu sirasi: FC 5x5, Sonuclar, 3x3, Arsiv. MENU_ORDER'da olmayan
  // bir lig eklenirse Arsiv'in onune duser.
  const byId = new Map(leagues.map((l) => [l.champ_id, l]))
  const known = MENU_ORDER.filter((x) => typeof x !== 'number' || byId.has(x))
  const others = leagues.filter((l) => !MENU_ORDER.includes(l.champ_id))
  const menu = [...known.slice(0, -1), ...others, known[known.length - 1]]
    .map((x) => (typeof x === 'number' ? byId.get(x) : PAGES[x]))
  // Ligler yuklenmeden "/" hedefini bilemeyiz; kayitli lig varsa onu kullan.
  const home = champ != null ? `/lig/${champ}` : null

  return (
    <div className="app">
      <header className="top">
        <div className="brand">Bet<span>Odds</span></div>
        <nav className="tabs">
          {menu.map((item) => item.to ? (
            <NavLink key={item.to} to={item.to}
              className={({ isActive }) => isActive ? 'active' : ''}>{item.label}</NavLink>
          ) : (
            <NavLink key={item.champ_id} to={`/lig/${item.champ_id}`}
              className={({ isActive }) => isActive ? 'active' : ''}
              title={item.name}>
              {item.short_name || item.name || item.champ_id}
            </NavLink>
          ))}
        </nav>

        <div className="status">
          {league && <span className="league-now">{league.name}</span>}
          {league?.season && (
            <span className="season-now" title={seasonTitle(league.season)}>
              {league.season.iteration}. sezon
            </span>
          )}
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
