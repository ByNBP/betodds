import { Link } from 'react-router-dom'
import { adjustText, fmtOdd, fmtTime } from '../format.js'

/**
 * Iki ayri sayi yan yana:
 *   Beklenti - mac oncesi oranlarin ima ettigi gol sayisi (bahiscinin modeli).
 *   Tahmin   - modelin harmanlanmis tahmini: sezon gucu + oran beklentisi +
 *              form (+ istenirse benzer oranli maclar). Bkz. backend/app/predict.py.
 *
 * Seviye "Tam Toplam Gol" (G=9939) marketinden gelir - tam bir market, kitap
 * toplami ~1.2 (yalnizca marj). Ev/deplasman payi Kesin Skor'dan (G=136)
 * alinir ama sadece ORAN olarak: o market sunulan skorlarla sinirli oldugu
 * icin seviyesi dusuk cikar, dagilimi ise saglikli.
 */
export default function GoalExpectation({ matches }) {
  const rows = (matches || []).filter((m) => m.expect)

  return (
    <div className="panel">
      <div className="chart-head"><h2>Gol beklentisi</h2></div>
      <div className="chart-sub">
        beklenti = maç öncesi oranlardan, marj çıkarılmış · tahmin = sezon gücü,
        oran beklentisi ve form harmanı · çizgi = beklentiye en yakın alt/üst ·
        kalan = geçen süreye göre eritilmiş beklenti
      </div>

      {rows.length === 0 ? (
        <div className="empty">Maç öncesi arşivi olan maç yok.</div>
      ) : (
        <div className="scroll-x" style={{ marginTop: 12 }}>
          <table>
            <thead>
              <tr>
                <th>Maç</th><th className="num">Ev</th><th className="num">Dep.</th>
                <th className="num" title="Maç öncesi oranların ima ettiği toplam">Beklenti</th>
                <th className="num"
                  title="Sezon gücü, oran beklentisi ve form harmanı — detay için tıklayın">
                  Tahmin</th>
                <th className="num">En olası</th>
                <th className="num" title="Beklentiye en yakın alt/üst çizgisi">Çizgi</th>
                <th className="num">Üst</th><th className="num">Alt</th>
                <th className="num" title="Maçın kalan süresinde beklenen gol">Kalan</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((m) => {
                const e = m.expect
                return (
                  <tr key={m.event_id}>
                    <td>
                      <Link to={`/mac/${m.event_id}`}>{m.home} – {m.away}</Link>
                      <span className="muted"> · {fmtTime(m.start_ts)}</span>
                    </td>
                    <td className="num">{e.home?.toFixed(2) ?? '—'}</td>
                    <td className="num">{e.away?.toFixed(2) ?? '—'}</td>
                    <td className="num" title={adjustText(e) || undefined}>
                      <strong>{e.total.toFixed(2)}</strong>
                      {e.total_raw != null && (
                        <div className="adjust-note">
                          {e.total_raw.toFixed(2)} − {e.adjust?.offset ?? 0.5}
                        </div>
                      )}
                    </td>
                    <td className="num">
                      {m.predict?.total != null ? (
                        <Link to={`/mac/${m.event_id}#tahmin`}
                          title="Sezon gücü + oran beklentisi + form harmanı">
                          <strong>{m.predict.total.toFixed(2)}</strong>
                        </Link>
                      ) : <span className="muted">—</span>}
                    </td>
                    <td className="num">{e.top_total}
                      <span className="muted"> %{e.top_prob}</span></td>
                    <td className="num">{e.line ?? '—'}</td>
                    <td className="num">{fmtOdd(e.line_over)}</td>
                    <td className="num">{fmtOdd(e.line_under)}</td>
                    <td className="num">
                      {e.remaining === null ? <span className="muted">—</span> : (
                        <>
                          <strong>{e.remaining.toFixed(2)}</strong>
                          <span className="muted"> {e.elapsed_min.toFixed(0)}. dk</span>
                        </>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
