import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api.js'
import { fmtDateTime, fmtOdd } from '../format.js'

/**
 * "Bu maca benzeyen gecmis maclarda kac gol geldi?"
 *
 * Benzerlik: baslangic (mac oncesi) 1 ve 2 oranlarinin her ikisi de +/-gap
 * icinde. Tahmin = o maclarin toplam gol ORTALAMASI. Ornegin tamami asagida
 * tek tek listeleniyor - sayinin nereden geldigi gorunur olsun diye.
 *
 * Berabere ayagi benzerlige katilmaz (bkz. backend/app/predict.py).
 */

const num = (v, d = 2) => (v === null || v === undefined ? '—' : Number(v).toFixed(d))

export default function SimilarOddsMatches({ match }) {
  const [gap, setGap] = useState('0.50')
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  const g = Number(gap) > 0 ? gap : '0.50'

  useEffect(() => {
    if (!match?.event_id) return
    let alive = true
    api.similar(match.event_id, g)
      .then((d) => alive && (setData(d), setError(null)))
      .catch((e) => alive && (setData(null), setError(e.message)))
    return () => { alive = false }
  }, [match?.event_id, g])

  if (error) {
    return (
      <div className="panel" id="benzer">
        <div className="chart-head"><h2>Benzer oranlı maçlar</h2></div>
        <div className="notice">{error}</div>
      </div>
    )
  }
  if (!data) return null

  const p = data.predict
  const expect = match.expect?.total
  const acc = p.accuracy
  const maxBin = Math.max(1, ...(p.histogram || []).map((h) => h.n))

  return (
    <div className="panel" id="benzer">
      <div className="chart-head"><h2>Benzer oranlı maçlar</h2></div>
      <div className="chart-sub">
        başlangıç oranı 1 {fmtOdd(data.p1)} · 2 {fmtOdd(data.p2)} — her ikisi de
        ±{g} içinde kalan biten maçlar · {p.pool} maçlık arşivden {p.n} tanesi
      </div>

      <div className="controls odds-filter" style={{ margin: '12px 0 4px' }}>
        <span className="muted">Pencere ±</span>
        <input type="number" step="0.05" min="0.05" max="5" value={gap}
          onChange={(e) => setGap(e.target.value)}
          title="Oran toleransı — genişletmek örneği büyütür, benzerliği zayıflatır" />
      </div>

      {p.n === 0 ? (
        <div className="empty">
          Bu orana ±{g} yakınlıkta, skoru bilinen biten maç yok. Pencereyi genişletin.
        </div>
      ) : (
        <>
          <div className="kv" style={{ marginTop: 12 }}>
            <div><div className="k">Tahmin (ortalama)</div>
              <div className="v">{num(p.total)}</div></div>
            <div><div className="k">Medyan</div><div className="v">{num(p.median)}</div></div>
            <div><div className="k">Aralık</div>
              <div className="v">{p.min} – {p.max}</div></div>
            <div><div className="k">Sapma</div><div className="v">±{num(p.stdev)}</div></div>
            <div><div className="k">Örnek</div><div className="v">{p.n} maç</div></div>
            {expect != null && (
              <div><div className="k">Oran beklentisi</div>
                <div className="v">{num(expect)}
                  <span className="muted"> ({num(p.total - expect)} fark)</span></div></div>
            )}
          </div>

          <h3 className="step">Örnekteki gol dağılımı</h3>
          <div className="scroll-x">
            <table>
              <thead>
                <tr><th>Toplam gol</th><th className="num">Maç</th><th>Dağılım</th></tr>
              </thead>
              <tbody>
                {p.histogram.map((h) => (
                  <tr key={h.goals}>
                    <td>{h.goals} gol</td>
                    <td className="num">{h.n}</td>
                    <td>
                      <span className="prob-bar" style={{ width: 160 }}>
                        <span style={{ width: `${(h.n / maxBin) * 100}%` }} />
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <h3 className="step">Örnekteki maçlar <span className="muted">(yakından uzağa)</span></h3>
          <div className="scroll-x">
            <table>
              <thead>
                <tr>
                  <th>Maç</th><th>Tarih</th>
                  <th className="num">1</th><th className="num">2</th>
                  <th className="num">Skor</th><th className="num">Gol</th>
                  <th className="num" title="|Δ1| + |Δ2|">Uzaklık</th>
                </tr>
              </thead>
              <tbody>
                {p.samples.map((s) => (
                  <tr key={s.event_id}>
                    <td><Link to={`/mac/${s.event_id}`}>{s.home} – {s.away}</Link></td>
                    <td className="muted">{fmtDateTime(s.start_ts)}</td>
                    <td className="num">{fmtOdd(s.p1)}</td>
                    <td className="num">{fmtOdd(s.p2)}</td>
                    <td className="num">{s.score_home} - {s.score_away}</td>
                    <td className="num"><strong>{s.total}</strong></td>
                    <td className="num muted">{num(s.dist)}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr>
                  <td><strong>Ortalama</strong></td>
                  <td colSpan="4" className="muted">{p.n} maçın toplam gol ortalaması</td>
                  <td className="num"><strong>{num(p.total)}</strong></td>
                  <td />
                </tr>
              </tfoot>
            </table>
          </div>
        </>
      )}

      {acc && acc.mae != null && (
        <div className="notice" style={{ marginTop: 16 }}>
          <strong>Bu yöntem ne kadar isabetli?</strong> Arşivdeki biten maçlarda,
          her maç kendisi dışarıda bırakılarak ölçüldü (n={acc.n}):
          ortalama hata <strong>{num(acc.mae)}</strong> gol.
          Hiç benzerlik kullanmayan taban — arşivin geneli ({num(acc.baseline_avg)} gol)
          — {num(acc.baseline_mae)} hata veriyor.
          {acc.mae > acc.baseline_mae && (
            <> Yani şu anki arşiv boyutunda benzer-oran seçimi tabandan{' '}
              <strong>daha iyi değil</strong>; örneklem büyüdükçe bu değişebilir.</>
          )}
        </div>
      )}
    </div>
  )
}
