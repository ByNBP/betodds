import { useEffect, useMemo, useState } from 'react'
import { api } from '../api.js'

export default function Stats({ champ, tourneyId }) {
  // Lig secimi GLOBAL (basliktaki secici); burada yalnizca gorunum sekmesi var.
  const [tab, setTab] = useState('form')

  return (
    <>
      <div className="controls">
        <button className={tab === 'form' ? 'primary' : ''} onClick={() => setTab('form')}>
          Takım formu (bizim arşiv)
        </button>
        <button className={tab === 'season' ? 'primary' : ''} onClick={() => setTab('season')}>
          Sezon tabloları (eventsstat)
        </button>
      </div>
      {tab === 'form'
        ? <TeamForm champId={champ} />
        : <Seasons tourneyId={tourneyId} />}
    </>
  )
}

function TeamForm({ champId }) {
  const [rows, setRows] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let alive = true
    setRows(null)
    api.teamStats(champId ?? undefined)
      .then((d) => alive && (setRows(d), setError(null)))
      .catch((e) => alive && setError(e.message))
    return () => { alive = false }
  }, [champId])

  if (error) return <div className="error">{error}</div>
  if (!rows) return <div className="empty">Yükleniyor…</div>
  if (!rows.length) {
    return (
      <div className="panel">
        <div className="empty">
          Henüz biten maç arşivlenmedi.<br />
          <span className="muted">Bu tablo, toplayıcının kaydettiği final skorlarından üretilir.</span>
        </div>
      </div>
    )
  }

  return (
    <div className="panel scroll-x">
      <div className="notice">
        Sitenin istatistik servisi bu sanal maçlar için veri döndürmüyor; aşağıdaki
        tablo tamamen bizim topladığımız final skorlarından hesaplanıyor.
      </div>
      <table>
        <thead>
          <tr>
            <th>Takım</th><th className="num">O</th><th className="num">G</th>
            <th className="num">B</th><th className="num">M</th><th className="num">P</th>
            <th className="num">Attığı</th><th className="num">Yediği</th>
            <th className="num">Maç başı gol</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.team}>
              <td>{r.team}</td>
              <td className="num">{r.played}</td><td className="num">{r.wins}</td>
              <td className="num">{r.draws}</td><td className="num">{r.losses}</td>
              <td className="num"><strong>{r.points}</strong></td>
              <td className="num">{r.avg_for}</td><td className="num">{r.avg_against}</td>
              <td className="num">{r.avg_total}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Seasons({ tourneyId }) {
  // Takim adlari ligden lige degisiyor; sabit bir ad on-doldurmak yeni ligde
  // hep bos tablo verirdi. Bos = sezon listesi.
  const [team, setTeam] = useState('')
  const [rows, setRows] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!tourneyId) { setRows([]); return undefined }
    let alive = true
    const t = setTimeout(() => {
      api.seasons(tourneyId, team || undefined)
        .then((d) => alive && (setRows(d), setError(null)))
        .catch((e) => alive && setError(e.message))
    }, 250)
    return () => { alive = false; clearTimeout(t) }
  }, [team, tourneyId])

  const totals = useMemo(() => {
    if (!rows?.length || !rows[0].team) return null
    const t = rows.reduce((a, r) => ({
      played: a.played + r.played, wins: a.wins + r.wins, draws: a.draws + r.draws,
      losses: a.losses + r.losses, gf: a.gf + r.gf, ga: a.ga + r.ga,
      pos: a.pos + r.pos, n: a.n + 1,
    }), { played: 0, wins: 0, draws: 0, losses: 0, gf: 0, ga: 0, pos: 0, n: 0 })
    const p = t.played || 1
    return {
      ...t,
      winPct: (100 * t.wins / p).toFixed(1),
      avgFor: (t.gf / p).toFixed(2),
      avgAgainst: (t.ga / p).toFixed(2),
      avgTotal: ((t.gf + t.ga) / p).toFixed(2),
      avgPos: (t.pos / (t.n || 1)).toFixed(1),
    }
  }, [rows])

  return (
    <>
      <div className="controls">
        <input placeholder="Takım (boş bırakırsan sezon listesi)" value={team}
          onChange={(e) => setTeam(e.target.value)} style={{ minWidth: 260 }} />
      </div>

      {error && <div className="error">{error}</div>}

      {totals && (
        <div className="panel">
          <h2>{team} — {totals.n} sezon toplamı</h2>
          <div className="kv">
            <div><div className="k">Maç</div><div className="v">{totals.played}</div></div>
            <div><div className="k">G / B / M</div>
              <div className="v">{totals.wins} / {totals.draws} / {totals.losses}</div></div>
            <div><div className="k">Galibiyet</div><div className="v">%{totals.winPct}</div></div>
            <div><div className="k">Maç başı attığı</div><div className="v">{totals.avgFor}</div></div>
            <div><div className="k">Maç başı yediği</div><div className="v">{totals.avgAgainst}</div></div>
            <div><div className="k">Maç başı toplam</div><div className="v">{totals.avgTotal}</div></div>
            <div><div className="k">Ortalama sıra</div><div className="v">{totals.avgPos}</div></div>
          </div>
        </div>
      )}

      <div className="panel scroll-x">
        {!rows ? <div className="empty">Yükleniyor…</div>
          : rows.length === 0 ? <div className="empty">Kayıt yok.</div>
          : rows[0].team ? (
            <table>
              <thead>
                <tr>
                  <th className="num">Sezon</th><th className="num">Sıra</th>
                  <th className="num">O</th><th className="num">G</th><th className="num">B</th>
                  <th className="num">M</th><th className="num">Attığı</th>
                  <th className="num">Yediği</th><th className="num">Averaj</th>
                  <th className="num">Puan</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.iteration}>
                    <td className="num">{r.iteration}</td>
                    <td className="num"><strong>{r.pos}</strong></td>
                    <td className="num">{r.played}</td><td className="num">{r.wins}</td>
                    <td className="num">{r.draws}</td><td className="num">{r.losses}</td>
                    <td className="num">{r.gf}</td><td className="num">{r.ga}</td>
                    <td className="num">{r.gf - r.ga > 0 ? '+' : ''}{r.gf - r.ga}</td>
                    <td className="num"><strong>{r.points}</strong></td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <table>
              <thead>
                <tr><th className="num">Sezon</th><th className="num">Takım</th>
                  <th className="num">Oynanan</th></tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.iteration}>
                    <td className="num">{r.iteration}</td>
                    <td className="num">{r.teams}</td>
                    <td className="num">{r.played}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
      </div>
    </>
  )
}
