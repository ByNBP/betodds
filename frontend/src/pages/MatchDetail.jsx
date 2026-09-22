import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api.js'
import useTitle from '../useTitle.js'
import { fmtDateTime, fmtOdd, impliedPct, scoreText, STATUS_LABEL } from '../format.js'
import MarketGroups from '../components/MarketGroups.jsx'
import ExpectationBreakdown from '../components/ExpectationBreakdown.jsx'
import SimilarOddsMatches from '../components/SimilarOddsMatches.jsx'
import PredictionBreakdown from '../components/PredictionBreakdown.jsx'

export default function MatchDetail({ pulse }) {
  const { id } = useParams()
  const [match, setMatch] = useState(null)
  const [odds, setOdds] = useState(null)
  const [oddsError, setOddsError] = useState(null)
  const [ticks, setTicks] = useState([])
  const [error, setError] = useState(null)
  // Mac yuklenene kadar baslik dokunulmadan kalir (bkz. useTitle).
  useTitle(match ? `${match.home} – ${match.away}` : null)

  useEffect(() => {
    let alive = true
    api.match(id)
      .then((d) => alive && (setMatch(d), setError(null)))
      .catch((e) => alive && setError(e.message))
    api.ticks(id).then((d) => alive && setTicks(d)).catch(() => {})
    api.odds(id)
      .then((d) => alive && (setOdds(d), setOddsError(null)))
      .catch((e) => alive && setOddsError(e.message))
    return () => { alive = false }
  }, [id, pulse])

  if (error) return <div className="error">Maç yüklenemedi: {error}</div>
  if (!match) return <div className="empty">Yükleniyor…</div>

  const open = ticks[0]
  const last = ticks[ticks.length - 1]

  return (
    <>
      <div style={{ marginBottom: 14 }}>
        <Link to="/arsiv" className="muted">← listeye dön</Link>
      </div>

      <div className="panel">
        <div className="row1" style={{ display: 'flex', gap: 10, alignItems: 'center',
          fontSize: 12, color: 'var(--muted)', marginBottom: 12 }}>
          <span className={`badge ${match.status === 'live' ? 'live' : ''}`}>
            {STATUS_LABEL[match.status] || match.status}
          </span>
          <span>{match.league_name}</span>
          <span>· {fmtDateTime(match.start_ts)}</span>
          {match.iteration ? <span>· sezon {match.iteration}</span> : null}
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr auto 1fr',
          alignItems: 'center', gap: 16, fontSize: 20, fontWeight: 700 }}>
          <div>{match.home}</div>
          <div style={{ fontSize: 30 }}>{scoreText(match)}</div>
          <div style={{ textAlign: 'right' }}>{match.away}</div>
        </div>

        {open && (
          <div className="kv" style={{ marginTop: 18 }}>
            <div><div className="k">Açılış 1</div><div className="v">{fmtOdd(open.o1)}</div></div>
            <div><div className="k">Açılış X</div><div className="v">{fmtOdd(open.ox)}</div></div>
            <div><div className="k">Açılış 2</div><div className="v">{fmtOdd(open.o2)}</div></div>
            <div><div className="k">Son 1</div><div className="v">{fmtOdd(last.o1)}</div></div>
            <div><div className="k">Ev sahibi olasılık</div>
              <div className="v">{impliedPct(open.o1)}</div></div>
            <div><div className="k">Kayıt</div>
              <div className="v">{match.tick_count} tick</div></div>
          </div>
        )}
      </div>

      <PredictionBreakdown predict={match.predict} expect={match.expect} />

      <ExpectationBreakdown expect={match.expect} />

      <SimilarOddsMatches match={match} />

      {odds?.settled && (
        <div className="panel">
          <h2>Sonuç</h2>
          <div className="final-score">
            <div>{match.home}</div>
            <div className="s">{odds.score.home} - {odds.score.away}</div>
            <div style={{ textAlign: 'right' }}>{match.away}</div>
          </div>
          <div className="kv" style={{ marginTop: 16 }}>
            <div><div className="k">Tutan</div>
              <div className="v" style={{ color: 'var(--good)' }}>{odds.tally.won}</div></div>
            <div><div className="k">Tutmayan</div><div className="v">{odds.tally.lost}</div></div>
            <div><div className="k">İade</div><div className="v">{odds.tally.void}</div></div>
            <div><div className="k">Belirlenemeyen</div>
              <div className="v">{odds.tally.unknown}</div></div>
          </div>
          {odds.winners.length > 0 && (
            <>
              <h3 style={{ marginTop: 18 }}>Tutan ihtimaller</h3>
              <div className="winners">
                {odds.winners.map((w, i) => (
                  <div className="winner" key={i}>
                    <span><span className="g">{w.group}</span><br />{w.label}</span>
                    <span className="v">{fmtOdd(w.coef)}</span>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      )}

      <div className="panel">
        <h2>
          {odds?.is_reference ? 'Referans oranlar (başlangıçtan hemen önce)'
                              : 'Maç öncesi tüm marketler'}
          {odds ? <span className="muted"> — {odds.market_count} oran, {odds.groups.length} grup</span> : null}
        </h2>
        {oddsError ? (
          <>
            <div className="notice">
              Bu maç için arşiv yok. Site, maç bittikten sonra oranları tamamen siliyor;
              bu yüzden oranlar yalnızca maç başlamadan önce yakalanabiliyor.
            </div>
            <div className="muted">{oddsError}</div>
          </>
        ) : odds ? (
          <>
            <div className="notice">
              {odds.is_reference
                ? <>Geçerli oranlar bunlar: maç başlamadan{' '}
                    <strong>{odds.seconds_before_kickoff}&nbsp;saniye</strong> önce alındı.
                    Maç içindeki oran değişimi referans değildir.</>
                : <>Referans set (başlangıçtan hemen önceki) yok; gösterilen set açılış
                    oranlarıdır — başlangıçtan{' '}
                    <strong>{Math.round((odds.seconds_before_kickoff || 0) / 60)}&nbsp;dakika</strong> önce alındı.</>}
              {odds.available_phases.length > 1 && (
                <> · kayıtlı fazlar: {odds.available_phases.map((a) => a.phase).join(', ')}</>
              )}
            </div>
            <MarketGroups groups={odds.groups} settled={odds.settled} />
          </>
        ) : <div className="empty">Yükleniyor…</div>}
      </div>
    </>
  )
}
