import { Link } from 'react-router-dom'
import { fmtOdd, fmtTime, scoreText, startText, STATUS_LABEL } from '../format.js'

// Renkli nokta = seri kimligi; sayi metin renginde kalir.
const ODDS = [
  { key: '1', field: 'o1', color: 'var(--series-1)' },
  { key: 'X', field: 'ox', color: 'var(--series-2)' },
  { key: '2', field: 'o2', color: 'var(--series-3)' },
]

export default function MatchCard({ m }) {
  const pending = m.score_home === null || m.score_home === undefined
  const when = startText(m)
  return (
    <Link to={`/mac/${m.event_id}`} className="card">
      <div className="row1">
        <span className={`badge ${m.status === 'live' ? 'live' : ''}`}>
          {STATUS_LABEL[m.status] || m.status}
        </span>
        <span>{fmtTime(m.start_ts)}</span>
        {when ? <span>· {when}</span> : null}
        {m.has_snapshot > 0 && (
          <span className="badge arch" title="Maç öncesi tüm marketler arşivlendi">arşiv</span>
        )}
      </div>

      {/* Birden fazla lig izleniyor: hangi maca baktigi kart uzerinde belli olmali. */}
      {m.league_name && <div className="row1 muted">{m.league_name}</div>}

      <div className="teams">
        <div className="team">{m.home}</div>
        <div className={`score ${pending ? 'pending' : ''}`}>{scoreText(m)}</div>
        <div className="team away">{m.away}</div>
      </div>

      {m.expect ? (
        <div className="expect">
          <span className="muted">beklenen gol</span>
          <strong>{m.expect.total.toFixed(2)}</strong>
          {m.expect.home !== null && (
            <span className="muted">
              {m.expect.home.toFixed(2)} – {m.expect.away.toFixed(2)}
            </span>
          )}
        </div>
      ) : <div className="expect muted">maç öncesi arşiv yok</div>}

      <div className="odds">
        {ODDS.map((o) => (
          <div className="odd" key={o.key}>
            <div className="k">
              <span className="swatch" style={{ background: o.color }} />
              {o.key}
            </div>
            <div className="v">{fmtOdd(m[o.field])}</div>
          </div>
        ))}
      </div>
    </Link>
  )
}
