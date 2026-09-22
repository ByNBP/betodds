import { Link } from 'react-router-dom'
import { adjustText, fmtOdd, fmtTime, scoreText, startText, STATUS_LABEL } from '../format.js'

// Renkli nokta = seri kimligi; sayi metin renginde kalir.
const ODDS = [
  { key: '1', field: 'o1', color: 'var(--series-1)' },
  { key: 'X', field: 'ox', color: 'var(--series-2)' },
  { key: '2', field: 'o2', color: 'var(--series-3)' },
]

/**
 * Takim adinin yanindaki lig sirasi.
 *
 * Sira macin OYNANDIGI sezonun tablosundan gelir; o sezon henuz cekilmemisse
 * backend en son bilinen sezona duser ve pos_current ile isaretler - bunu
 * baslikta soyluyoruz, guncel sezonun sirasi sanilmasin.
 */
function Pos({ n, current, iteration }) {
  if (n == null) return null
  return (
    <span className="team-pos"
          title={current
            ? `lig sırası ${n} · en son bilinen sezon tablosundan (${iteration}. sezon)`
            : `lig sırası ${n} · maçın oynandığı sezon (${iteration})`}>
      {n}.
    </span>
  )
}

export default function MatchCard({ m }) {
  const pending = m.score_home === null || m.score_home === undefined
  const when = startText(m)
  // Mac basladiktan sonra asagidaki 1/X/2 kutulari MAC ICI orani gosteriyor;
  // baslangictaki fiyat isim altina yaziliyor ki oranin nereden nereye
  // gittigi gorulebilsin. Baslamamis macta ikisi ayni sey, tekrar etmiyoruz.
  const started = m.status === 'live'
  const startOdds = started && m.p1 !== null && m.p1 !== undefined
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

      <div className="teams" title={startOdds ? 'alttaki küçük sayılar: maç öncesi başlangıç oranı' : undefined}>
        <div className="team">
          {m.home}
          <Pos n={m.home_pos} current={m.pos_current} iteration={m.pos_iteration} />
          {startOdds && <div className="start-odd">{fmtOdd(m.p1)}</div>}
        </div>
        <div className={`score ${pending ? 'pending' : ''}`}>
          {scoreText(m)}
          {startOdds && <div className="start-odd">{fmtOdd(m.px)}</div>}
        </div>
        <div className="team away">
          <Pos n={m.away_pos} current={m.pos_current} iteration={m.pos_iteration} />
          {m.away}
          {startOdds && <div className="start-odd">{fmtOdd(m.p2)}</div>}
        </div>
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
          {/* Kalibrasyon islemi acikca yaziliyor: gosterilen sayi ham
              market beklentisi DEGIL, ondan turetilmis bir deger. */}
          {m.expect.total_raw != null && (
            <span className="adjust-note" title={adjustText(m.expect)}>
              ({m.expect.total_raw.toFixed(2)} − {m.expect.adjust?.offset ?? 0.5})
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
