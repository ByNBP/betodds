import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api.js'
import Coverage from '../components/Coverage.jsx'
import GoalStats from '../components/GoalStats.jsx'
import LeagueSwitch from '../components/LeagueSwitch.jsx'
import { fmtDateTime, fmtOdd, scoreText, STATUS_LABEL } from '../format.js'
import useTitle from '../useTitle.js'

const EMPTY_ODDS = { o1: '', ox: '', o2: '' }

export default function Archive({ champ, leagues, onChamp }) {
  useTitle('Arşiv')
  // Arsiv tek sayfa oldugu icin lig anahtari SAYFA ICINDE. Anahtar uygulama
  // genelindeki secimi degistirir (basliktaki lig adi ve Istatistik sayfasi
  // da onu izler) - iki ayri lig durumu tutmak, hangisinin gecerli oldugunu
  // belirsiz birakirdi.
  const [rows, setRows] = useState(null)
  const [stats, setStats] = useState(null)
  const [team, setTeam] = useState('')
  const [status, setStatus] = useState('')
  const [archive, setArchive] = useState('')
  const [odds, setOdds] = useState(EMPTY_ODDS)
  const [gap, setGap] = useState('0.25')
  const [error, setError] = useState(null)

  // Oran filtresi sunucuda: tum arsivde arar, sayfaya gelen ilk 200 kayitta degil.
  const oddsOn = Boolean(odds.o1 || odds.ox || odds.o2)
  // Kutu bosaltilirsa ya da 0 girilirse sunucu 422 dondurur; varsayilana duseriz.
  const gapNum = Number(gap) > 0 ? gap : '0.25'

  useEffect(() => {
    let alive = true
    const t = setTimeout(() => {
      const q = {
        team, champ_id: champ ?? '', status,
        o1: odds.o1, ox: odds.ox, o2: odds.o2,
        gap: oddsOn ? gapNum : '',
      }
      api.matches({ ...q, limit: 200 })
        .then((d) => alive && (setRows(d), setError(null)))
        .catch((e) => alive && setError(e.message))
      // Ozet ayri istek: tabloda 200 kayit gosterilse de filtrenin tamamini kapsar.
      api.matchStats(q)
        .then((d) => alive && setStats(d))
        .catch(() => alive && setStats(null))
    }, 250)                       // yazarken her tusa istek atmayalim
    return () => { alive = false; clearTimeout(t) }
  }, [team, champ, status, odds.o1, odds.ox, odds.o2, gapNum, oddsOn])

  // Arsiv filtresi istemci tarafinda: sunucu sorgusunu karmasiklastirmaya degmez
  const visible = (rows || []).filter((m) =>
    archive === 'with' ? m.snapshot_markets
      : archive === 'without' ? !m.snapshot_markets
        : true)

  const setOdd = (k) => (e) => setOdds((o) => ({ ...o, [k]: e.target.value }))

  return (
    <>
      <LeagueSwitch leagues={leagues} champ={champ} onChange={onChamp} />

      <Coverage champ={champ} />

      <div className="controls" style={{ marginTop: 16 }}>
        <input placeholder="Takım ara…" value={team}
          onChange={(e) => setTeam(e.target.value)} />
        <select value={archive} onChange={(e) => setArchive(e.target.value)}>
          <option value="">Tüm kayıtlar</option>
          <option value="with">Arşivi olan</option>
          <option value="without">Arşivi olmayan</option>
        </select>
        <select value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">Tüm durumlar</option>
          <option value="finished">Bitti</option>
          <option value="live">Canlı</option>
          <option value="scheduled">Başlamadı</option>
        </select>
      </div>

      <div className="controls odds-filter">
        <span className="muted">Maç öncesi oran:</span>
        <input type="number" step="0.01" min="1" placeholder="1"
          value={odds.o1} onChange={setOdd('o1')} title="Ev sahibi oranı" />
        <input type="number" step="0.01" min="1" placeholder="X"
          value={odds.ox} onChange={setOdd('ox')} title="Beraberlik oranı" />
        <input type="number" step="0.01" min="1" placeholder="2"
          value={odds.o2} onChange={setOdd('o2')} title="Deplasman oranı" />
        <span className="muted">± </span>
        <input type="number" step="0.05" min="0.01" value={gap}
          onChange={(e) => setGap(e.target.value)} title="Tolerans (gap)" />
        {oddsOn && (
          <>
            <button onClick={() => setOdds(EMPTY_ODDS)}>Temizle</button>
            <span className="muted">
              girilen her oran için ±{gapNum} · {visible.length} maç
            </span>
          </>
        )}
      </div>

      {error && <div className="error">{error}</div>}

      <GoalStats stats={stats} />

      <div className="panel scroll-x">
        {!rows ? <div className="empty">Yükleniyor…</div>
          : visible.length === 0 ? <div className="empty">Kayıt bulunamadı.</div> : (
          <table>
            <thead>
              <tr>
                <th>Tarih</th><th>Ev sahibi</th><th className="num">Skor</th><th>Deplasman</th>
                <th>Durum</th>
                <th className="num" title="Maç öncesi (kickoff) oranı">1</th>
                <th className="num" title="Maç öncesi (kickoff) oranı">X</th>
                <th className="num" title="Maç öncesi (kickoff) oranı">2</th>
                {oddsOn && <th className="num" title="Girilen oranlara toplam uzaklık">Fark</th>}
                <th title="Kitabın açtığı en düşük Alt çizgisi (skordan bağımsız)">İlk alt</th>
                <th title="Kitabın açtığı en yüksek Üst çizgisi (skordan bağımsız)">Son üst</th>
                <th title="Toplam golü geçen en düşük alt çizgisi">Tutan alt</th>
                <th title="Tutan üst çizgilerinin en yükseği">Tutan üst</th>
                <th>Arşiv</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((m) => (
                <tr key={m.event_id}>
                  <td className="muted">{fmtDateTime(m.start_ts)}</td>
                  <td><Link to={`/mac/${m.event_id}`}>{m.home}</Link></td>
                  <td className="num"><strong>{scoreText(m)}</strong></td>
                  <td><Link to={`/mac/${m.event_id}`}>{m.away}</Link></td>
                  <td>{STATUS_LABEL[m.status] || m.status}</td>
                  <td className="num">{fmtOdd(m.p1)}</td>
                  <td className="num">{fmtOdd(m.px)}</td>
                  <td className="num">{fmtOdd(m.p2)}</td>
                  {oddsOn && (
                    <td className="num muted">
                      {m.odds_dist === null || m.odds_dist === undefined
                        ? '—' : m.odds_dist.toFixed(2)}
                    </td>
                  )}
                  {/* Kitabin uclari skora bakmaz: yaklasan maclarda da dolu. */}
                  <td>{m.book_under_first
                    ? <>Alt {m.book_under_first} <span className="muted">@{fmtOdd(m.book_under_first_odd)}</span></>
                    : <span className="muted">—</span>}</td>
                  <td>{m.book_over_last
                    ? <>Üst {m.book_over_last} <span className="muted">@{fmtOdd(m.book_over_last_odd)}</span></>
                    : <span className="muted">—</span>}</td>
                  <td>{m.under_first
                    ? <>Alt {m.under_first} <span className="muted">@{fmtOdd(m.under_first_odd)}</span></>
                    : <span className="muted">—</span>}</td>
                  <td>{m.over_top
                    ? <>Üst {m.over_top} <span className="muted">@{fmtOdd(m.over_top_odd)}</span></>
                    : <span className="muted">—</span>}</td>
                  <td>{m.snapshot_markets
                    ? <span className="badge arch">{m.snapshot_markets} oran</span>
                    : m.status === 'scheduled'
                      ? <span className="muted">bekleniyor</span>
                      : <span className="muted" title="Maç bitti, oranlar silindi">yok</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  )
}
