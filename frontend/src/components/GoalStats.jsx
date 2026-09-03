import { fmtOdd } from '../format.js'

/**
 * Filtreye giren maclarin gol ve alt/ust ozeti.
 *
 * Ozet, tabloda gosterilen ilk N kaydin degil filtrenin TAMAMININ ustunden
 * hesaplanir (sunucu tarafinda, limitsiz) - bu yuzden ayri bir istek.
 */
export default function GoalStats({ stats, title, subtitle, empty }) {
  if (!stats || !stats.goals) {
    return empty ? <div className="panel"><div className="chart-head">
      <h2>{title || 'Gol istatistikleri'}</h2></div>
      <div className="empty">{empty}</div></div> : null
  }
  const g = stats.goals

  const rows = [
    ['Ev sahibi', g.home],
    ['Deplasman', g.away],
    ['Toplam', g.total],
  ]

  return (
    <div className="panel">
      <div className="chart-head"><h2>{title || 'Gol istatistikleri'}</h2></div>
      <div className="chart-sub">
        {subtitle ? <>{subtitle} · </> : null}
        {stats.matches} maç · {stats.scored} tanesinin skoru biliniyor
        {stats.archived > 0 && ` · ${stats.archived} tanesinde alt/üst arşivi var`}
      </div>

      <div className="grid-2" style={{ marginTop: 14 }}>
        <div>
          <table>
            <thead>
              <tr><th>Gol</th><th className="num">En az</th>
                <th className="num">En çok</th><th className="num">Ortalama</th></tr>
            </thead>
            <tbody>
              {rows.map(([k, v]) => (
                <tr key={k}>
                  <td>{k}</td>
                  <td className="num">{v.min}</td>
                  <td className="num">{v.max}</td>
                  <td className="num"><strong>{v.avg}</strong></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div>
          {stats.common_lines.length > 0 ? (
            <table>
              <thead>
                <tr><th>Ortak çizgi</th><th className="num">Üst ort.</th>
                  <th className="num">Alt ort.</th>
                  <th className="num" title="Bu çizgiyi kaç maçta üst / alt götürdü">
                    Üst–Alt</th></tr>
              </thead>
              <tbody>
                {stats.common_lines.map((l) => (
                  <tr key={l.line}>
                    <td>{l.line}</td>
                    <td className="num">{fmtOdd(l.over_avg)}</td>
                    <td className="num">{fmtOdd(l.under_avg)}</td>
                    <td className="num">
                      <span style={{ color: l.over_won >= l.under_won
                        ? 'var(--up)' : undefined }}>{l.over_won}</span>
                      <span className="muted"> – </span>
                      <span style={{ color: l.under_won > l.over_won
                        ? 'var(--up)' : undefined }}>{l.under_won}</span>
                      {l.push > 0 && <span className="muted"> ({l.push} iade)</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="empty" style={{ padding: 20 }}>
              Bu maçlarda ortak alt/üst çizgisi yok.
            </div>
          )}
        </div>
      </div>

      {stats.archived > 0 && (
        <div className="kv" style={{ marginTop: 16 }}>
          <Hits title="İlk tutan alt" rows={stats.under_first} side="Alt"
            avg={stats.under_first_avg} none={stats.no_under}
            noneLabel="maçta hiçbir alt tutmadı" />
          <Hits title="En üstte tutan üst" rows={stats.over_top} side="Üst"
            avg={stats.over_top_avg} none={stats.no_over}
            noneLabel="maçta hiçbir üst tutmadı" />
        </div>
      )}

      <div className="notice" style={{ marginTop: 14, marginBottom: 0 }}>
        <strong>İlk tutan alt</strong>, toplam golü geçen en düşük alt çizgisidir
        (toplam 7 ise Alt 7.5). <strong>En üstte tutan üst</strong> ise tutan üst
        çizgilerinin en yükseği (toplam 7 ise Üst 6.5). Oranlar maç öncesi
        referans setinden; <strong>ortak çizgi</strong>, arşivi olan tüm maçlarda
        birden bulunan çizgidir. <strong>Üst–Alt</strong> sütunu o çizgiyi kaç maçta
        üstün, kaç maçta altın götürdüğünü gösterir.
      </div>
    </div>
  )
}

function Hits({ title, rows, side, avg, none, noneLabel }) {
  const total = rows.reduce((s, r) => s + r.count, 0)
  return (
    <div style={{ gridColumn: 'span 2' }}>
      <div className="k">{title}{avg !== null && ` · ortalama çizgi ${avg}`}</div>
      <div className="v" style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 4 }}>
        {rows.length === 0 && <span className="muted">—</span>}
        {rows.map((r) => (
          <span className="badge arch" key={r.line}>
            {side} {r.line} · {r.count}
            <span className="muted"> %{Math.round((r.count / total) * 100)}</span>
          </span>
        ))}
        {none > 0 && <span className="muted" style={{ fontSize: 12 }}>
          {none} {noneLabel}</span>}
      </div>
    </div>
  )
}
