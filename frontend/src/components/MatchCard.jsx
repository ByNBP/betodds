import { Link } from 'react-router-dom'
import { adjustText, fmtGoal, fmtOdd, fmtTime, isFavoriteMatch, isHighGoal, scoreText,
  startText, STATUS_LABEL } from '../format.js'

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

const pct = (v) => `%${Math.round(v * 100)}`

/**
 * Sag ust kose: kazanma olasiligi yuksek olan taraf. Olasilik modelin MAC
 * ONCESI gol tahmininden (bkz. predict.outcome_probs); mac basladiktan sonra
 * da degismez. Uc olasiligin tamami baslikta.
 */
function WinPick({ m }) {
  const w = m.win
  if (!w) return null
  const team = w.pick === 'home' ? m.home : m.away
  return (
    <span className="win-pick"
          title={`Maç öncesi tahmini kazanma olasılığı`
            + ` · ${m.home} ${pct(w.home)} · beraberlik ${pct(w.draw)} · ${m.away} ${pct(w.away)}`}>
      <span className="win-team">{team}</span> {pct(w[w.pick])}
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
        {/* Sag ust kose: kazanan tahmini, altinda "favori maç" etiketi. Ust
            uste duruyorlar ki satir daralip durum metnini sikistirmasin. */}
        <div className="corner">
          <WinPick m={m} />
          {isFavoriteMatch(m) && (
            <span className="badge fav fav-match"
                  title="Favori oranı 1.80–1.95 arası · iki takımın istatistik gol farkı 0.50 altı · ham değer ≥ 7.50">
              favori maç</span>
          )}
          {isHighGoal(m) && (
            <span className="badge surprise high-goal"
                  title="3x3 ligi · ev sahibi oranı 2.18">
              yüksek gol</span>
          )}
        </div>
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
          <span className="muted">istatistik gol sayısı</span>
          <strong title={adjustText(m.expect) || undefined}>{fmtGoal(m.expect.total)}</strong>
          {/* Mavi: macin kalibrasyon oncesi ham toplam gol beklentisi. */}
          {m.expect.total_raw != null && (
            <span className="adjust-note" title={adjustText(m.expect) || undefined}>
              ({m.expect.total_raw.toFixed(2)})
            </span>
          )}
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
