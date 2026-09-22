
/**
 * "Tahmin nasil olustu" paneli.
 *
 * Bes bilesen, agirliklari ve her birinin arsivde tek basina olculen isabeti
 * yan yana. Amac: tek bir sayiya bakip guvenmek yerine, o sayinin hangi
 * etmenden ne kadar geldigini ve o etmenin gecmiste ne kadar tuttugunu
 * gorebilmek.
 *
 * Tum degerler backend'den (predict.Predictor) gelir; burada yeniden hesap yok.
 */

const num = (v, d = 2) => (v === null || v === undefined ? '—' : Number(v).toFixed(d))

export default function PredictionBreakdown({ predict, expect }) {
  if (!predict) return null
  const comps = predict.components || {}
  const acc = predict.accuracy
  const cacc = predict.component_accuracy || {}
  const order = ['season', 'odds', 'form', 'similar', 'venue']
  const season = comps.season?.detail
  const form = comps.form?.detail

  return (
    <div className="panel" id="tahmin">
      <div className="chart-head"><h2>Tahmin nasıl oluştu</h2></div>
      <div className="chart-sub">
beş etmenin ağırlıklı harmanı · çarpanlar elle ayarlandı ·
        üretilemeyen etmenin ağırlığı kalanlara oransal dağıtılır
      </div>

      <div className="kv" style={{ marginTop: 14 }}>
        <div><div className="k">Tahmin</div><div className="v">{num(predict.total)}</div></div>
        <div><div className="k">Ev sahibi</div><div className="v">{num(predict.home)}</div></div>
        <div><div className="k">Deplasman</div><div className="v">{num(predict.away)}</div></div>
        <div><div className="k">Ev payı</div><div className="v">%{predict.home_share ?? '—'}</div></div>
        {expect?.total != null && (
          <div><div className="k">Oran beklentisi</div>
            <div className="v">{num(expect.total)}
              <span className="muted"> ({num(predict.total - expect.total)})</span></div></div>
        )}
      </div>

      <h3 className="step">Etmenler ve çarpanları</h3>
      <div className="scroll-x">
        <table>
          <thead>
            <tr>
              <th>Etmen</th>
              <th className="num" title="Ayarlanan çarpan">Çarpan</th>
              <th className="num" title="Eksik etmenler çıkarıldıktan sonra kullanılan">Etkin</th>
              <th className="num">Kendi tahmini</th>
              <th className="num" title="etkin çarpan × kendi tahmini">Katkı</th>
              <th className="num" title="Bu etmen TEK BAŞINA kullanılsaydı ortalama hata">
                Tek başına hata</th>
            </tr>
          </thead>
          <tbody>
            {order.map((k) => {
              const c = comps[k]
              const a = cacc[k]
              const eff = c?.effective ?? 0
              return (
                <tr key={k} className={eff > 0 ? 'hot' : undefined}>
                  <td>{a?.label || c?.label || k}
                    {!c && <span className="muted"> · veri yok</span>}</td>
                  <td className="num">{num(a?.weight ?? c?.weight ?? 0, 2)}</td>
                  <td className="num">{eff > 0 ? num(eff, 2)
                    : <span className="muted">—</span>}</td>
                  <td className="num">{c ? num(c.total) : '—'}</td>
                  <td className="num">{c && eff > 0 ? num(eff * c.total) : '—'}</td>
                  <td className="num muted">{a?.mae != null
                    ? <>{num(a.mae)} <span className="muted">n={a.n}</span></> : '—'}</td>
                </tr>
              )
            })}
          </tbody>
          <tfoot>
            <tr>
              <td><strong>Toplam</strong></td>
              <td className="num" />
              <td className="num">1.00</td>
              <td className="num" />
              <td className="num"><strong>{num(predict.total)}</strong></td>
              <td className="num">{acc?.mae != null ? <strong>{num(acc.mae)}</strong> : '—'}</td>
            </tr>
          </tfoot>
        </table>
      </div>

      {season && (
        <>
          <h3 className="step">Sezon gücü <span className="muted">(nasıl çıktı)</span></h3>
          <div className="step-note">
            Son {season.seasons} sezonun puan durumundan; güncel sezon ({season.current})
            ağırlığı {num(season.current_weight, 2)}. Atak = attığı gol, defans = yediği gol,
            ikisi de lig ortalamasına oranlanmış. Lig ortalaması takım başına{' '}
            <strong>{num(season.mu)}</strong> gol.
          </div>
          <div className="formula">
            ev = {num(season.mu)} × {num(season.att_home, 3)} × {num(season.def_away, 3)}
            {' = '}<strong>{num(comps.season.home)}</strong>
            <br />
            dep = {num(season.mu)} × {num(season.att_away, 3)} × {num(season.def_home, 3)}
            {' = '}<strong>{num(comps.season.away)}</strong>
          </div>
          <div className="scroll-x" style={{ marginTop: 12 }}>
            <table>
              <thead>
                <tr><th>Takım</th><th className="num">Atak</th><th className="num">Defans</th></tr>
              </thead>
              <tbody>
                <tr>
                  <td>ev sahibi</td>
                  <td className="num">{num(season.att_home, 3)}</td>
                  <td className="num">{num(season.def_home, 3)}</td>
                </tr>
                <tr>
                  <td>deplasman</td>
                  <td className="num">{num(season.att_away, 3)}</td>
                  <td className="num">{num(season.def_away, 3)}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div className="step-note" style={{ marginTop: 8 }}>
            1.00 = lig ortalaması. Atakta yüksek olan golcü, defansta yüksek olan
            çok gol yiyen demektir.
          </div>
        </>
      )}

      {form && (
        <>
          <h3 className="step">Form <span className="muted">(bizim arşivimizdeki lig maçları)</span></h3>
          <div className="step-note">
            Ev sahibi {form.home_played} maç, deplasman {form.away_played} maç kayıtlı.
            Az maç oynamış takım lig ortalamasına ({num(form.league_avg)}) çekiliyor —
            büzüşme <code>n / (n + {num(form.shrink_k, 0)})</code>.
          </div>
          <div className="scroll-x">
            <table>
              <thead>
                <tr><th>Takım</th><th className="num">Maç</th>
                  <th className="num">Attığı</th><th className="num">Yediği</th></tr>
              </thead>
              <tbody>
                <tr><td>ev sahibi</td><td className="num">{form.home_played}</td>
                  <td className="num">{num(form.home_scored)}</td>
                  <td className="num">{num(form.home_conceded)}</td></tr>
                <tr><td>deplasman</td><td className="num">{form.away_played}</td>
                  <td className="num">{num(form.away_scored)}</td>
                  <td className="num">{num(form.away_conceded)}</td></tr>
              </tbody>
            </table>
          </div>
        </>
      )}

      {acc && acc.mae != null && (
        <div className="notice" style={{ marginTop: 18 }}>
          <strong>Model ne kadar isabetli?</strong> Arşivdeki {acc.n} biten maçta, her maç
          kendisi dışarıda bırakılarak ölçüldü: ortalama hata <strong>{num(acc.mae)}</strong> gol.
          Hiçbir şey kullanmayan taban — arşiv geneli {num(acc.baseline_avg)} gol —{' '}
          {num(acc.baseline_mae)} hata veriyor.
          <br />
          <span className="muted">
            Bu büyüklükteki örneklemde MAE'nin kendi belirsizliği ±0.18 civarı; etmenler
            arasındaki küçük farklar istatistiksel olarak anlamlı değil. Çarpanlar{' '}
            <code>BETODDS_W_ODDS</code>, <code>BETODDS_W_SEASON</code>,{' '}
            <code>BETODDS_W_FORM</code>, <code>BETODDS_W_SIMILAR</code> ile değiştirilebilir.
          </span>
        </div>
      )}
    </div>
  )
}
