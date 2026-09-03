import { fmtDateTime, fmtOdd } from '../format.js'

/**
 * "Bu beklenti nereden cikti?" paneli.
 *
 * Gol beklentisi tablosundaki sayilarin dayandigi her ara deger burada tek tek
 * gosterilir. Hicbir sey burada yeniden hesaplanmaz - hepsi backend'in
 * goal_expectation(detail=True) ciktisindan gelir; aksi halde tablodaki deger
 * ile kirilimin toplami zamanla ayrisirdi.
 */

const pct = (v) => (v === null || v === undefined ? '—' : `%${v.toFixed(2)}`)
const num = (v, d = 2) => (v === null || v === undefined ? '—' : v.toFixed(d))

/** Olasilik hucresinin arkasindaki ince oran cubugu. */
function Bar({ value, max }) {
  const w = max > 0 ? Math.max(2, (value / max) * 100) : 0
  return (
    <span className="prob-bar" aria-hidden="true">
      <span style={{ width: `${w}%` }} />
    </span>
  )
}

export default function ExpectationBreakdown({ expect }) {
  if (!expect) return null
  const d = expect.detail
  if (!d) return null

  const tm = d.total_market
  const sm = d.score_market
  const ln = d.line
  const snap = expect.snapshot
  const maxProb = Math.max(...tm.bins.map((b) => b.prob_pct))

  return (
    <div className="panel">
      <div className="chart-head"><h2>Gol beklentisi nasıl hesaplandı</h2></div>
      <div className="chart-sub">
        maç öncesi tek bir oran setinden · marj oransal olarak çıkarılmış ·
        aşağıdaki her sayı hesabın gerçek girdisi
      </div>

      <div className="kv" style={{ marginTop: 14 }}>
        <div><div className="k">Toplam</div><div className="v">{num(expect.total)}</div></div>
        <div><div className="k">Ev sahibi</div><div className="v">{num(expect.home)}</div></div>
        <div><div className="k">Deplasman</div><div className="v">{num(expect.away)}</div></div>
        <div><div className="k">En olası</div>
          <div className="v">{expect.top_total} <span className="muted">%{expect.top_prob}</span></div></div>
        {expect.remaining !== null && expect.remaining !== undefined && (
          <div><div className="k">Kalan</div><div className="v">{num(expect.remaining)}</div></div>
        )}
      </div>

      {snap && (
        <div className="notice" style={{ marginTop: 16 }}>
          Kaynak: <strong>{snap.is_reference
            ? 'referans set (başlangıçtan hemen önce)'
            : 'açılış seti'}</strong> — {fmtDateTime(snap.taken_at)}
          {snap.seconds_before_kickoff !== null && snap.seconds_before_kickoff !== undefined && (
            <> · başlamadan {snap.seconds_before_kickoff >= 120
              ? `${Math.round(snap.seconds_before_kickoff / 60)} dakika`
              : `${snap.seconds_before_kickoff} saniye`} önce</>
          )} · {snap.market_count} oran.
          Maç bittikten sonra site oranları sildiği için başka kaynak yok.
        </div>
      )}

      {/* -------------------------------------------------- 1) seviye */}
      <h3 className="step">1 · Seviye — {tm.label} <span className="muted">(G={tm.g})</span></h3>
      <div className="step-note">
        Bu markette seçeneğin parametresi doğrudan maçın toplam gol sayısı ve market tam:
        {' '}{tm.n} seçenek, kitap toplamı {tm.book.toFixed(3)} (fazlalık yalnızca marj).
        Her oran <code>1/oran</code> ile olasılığa çevrilip kitap toplamına bölünüyor,
        sonra <code>Σ gol × olasılık</code> alınıyor.
      </div>
      <div className="scroll-x">
        <table>
          <thead>
            <tr>
              <th>Gol</th><th className="num">Oran</th>
              <th className="num" title="1/oran — marj dahil">Ham</th>
              <th className="num" title="Kitap toplamına bölünmüş">Marjsız</th>
              <th className="num" title="gol × olasılık">Katkı</th>
            </tr>
          </thead>
          <tbody>
            {tm.bins.map((b) => (
              <tr key={b.goals} className={b.goals === expect.top_total ? 'hot' : undefined}>
                <td>{b.goals} gol</td>
                <td className="num">{fmtOdd(b.coef)}</td>
                <td className="num muted">{pct(b.raw_pct)}</td>
                <td className="num">
                  <Bar value={b.prob_pct} max={maxProb} />
                  {pct(b.prob_pct)}
                </td>
                <td className="num">{num(b.contrib, 3)}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <td><strong>Toplam</strong></td>
              <td className="num muted">marj %{tm.margin_pct}</td>
              <td className="num muted">{tm.book.toFixed(3)}</td>
              <td className="num">%100</td>
              <td className="num"><strong>{num(tm.expected, 3)}</strong></td>
            </tr>
          </tfoot>
        </table>
      </div>

      {/* --------------------------------------------------- 2) pay */}
      {sm ? (
        <>
          <h3 className="step">2 · Ev/deplasman payı — {sm.label} <span className="muted">(G={sm.g})</span></h3>
          <div className="step-note">
            Kesin skor marketi sunulan {sm.n} skorla sınırlı, üstü kesik: kendi başına
            toplamı <strong>{num(sm.own_total)}</strong> veriyor, yani seviyeden
            {' '}{num((expect.total ?? 0) - sm.own_total)} gol düşük. Bu yüzden buradan
            yalnızca <strong>oran</strong> alınıyor, seviye 1. adımdan geliyor.
          </div>
          <div className="kv">
            <div><div className="k">E[ev] (ham)</div><div className="v">{num(sm.eh, 3)}</div></div>
            <div><div className="k">E[dep] (ham)</div><div className="v">{num(sm.ea, 3)}</div></div>
            <div><div className="k">Ev payı</div><div className="v">%{sm.home_share_pct}</div></div>
            <div><div className="k">Ev = toplam × pay</div>
              <div className="v">{num(expect.total)} × %{sm.home_share_pct} = {num(expect.home)}</div></div>
          </div>
          <details className="more">
            <summary>{sm.n} skorun olasılıkları</summary>
            <div className="scroll-x">
              <table>
                <thead>
                  <tr><th>Skor</th><th className="num">Oran</th><th className="num">Marjsız</th></tr>
                </thead>
                <tbody>
                  {sm.scores.map((s) => (
                    <tr key={s.label}>
                      <td>{s.label}</td>
                      <td className="num">{fmtOdd(s.coef)}</td>
                      <td className="num">{pct(s.prob_pct)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        </>
      ) : (
        <>
          <h3 className="step">2 · Ev/deplasman payı</h3>
          <div className="step-note">
            Bu snapshot'ta kesin skor marketi (G={136}) yok — pay hesaplanamadı,
            yalnızca toplam gösteriliyor.
          </div>
        </>
      )}

      {/* -------------------------------------------------- 3) cizgi */}
      {ln && (
        <>
          <h3 className="step">3 · Gösterilen çizgi — {ln.label} <span className="muted">(G={ln.g})</span></h3>
          <div className="step-note">
            Beklentiye ({num(expect.total)}) en yakın alt/üst çizgisi seçilir;
            eşit uzaklıkta iki çizgi olursa küçük olan.
          </div>
          <div className="scroll-x">
            <table>
              <thead>
                <tr>
                  <th>Çizgi</th>
                  <th className="num" title="|çizgi − beklenti|">Uzaklık</th>
                  <th className="num">Üst</th><th className="num">Alt</th>
                </tr>
              </thead>
              <tbody>
                {ln.candidates.map((c) => (
                  <tr key={c.line} className={c.chosen ? 'hot' : undefined}>
                    <td>{c.line}{c.chosen && <span className="muted"> · seçilen</span>}</td>
                    <td className="num">{num(c.distance, 3)}</td>
                    <td className="num">{fmtOdd(c.over)}</td>
                    <td className="num">{fmtOdd(c.under)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* -------------------------------------------------- 4) kalan */}
      {expect.remaining !== null && expect.remaining !== undefined && (
        <>
          <h3 className="step">4 · Kalan gol beklentisi</h3>
          <div className="step-note">
            Maç uzunluğu arşivden ölçüldü ({expect.match_minutes} dk medyan). Beklenti
            geçen süreyle doğrusal eritiliyor; <strong>atılan gol sayısı kullanılmıyor</strong>
            {' '}— Poisson sürecinde geçmiş gol geleceği değiştirmez.
          </div>
          <div className="formula">
            {num(expect.total)} × (1 − {num(expect.elapsed_min, 1)} / {expect.match_minutes})
            {' = '}{num(expect.total)} × {num(expect.left_share, 3)}
            {' = '}<strong>{num(expect.remaining)}</strong>
          </div>
        </>
      )}

      <div className="step-note" style={{ marginTop: 18 }}>
        Not: bunlar bahisçinin oranlarının ima ettiği beklentidir, bağımsız bir model
        değil. Marj oransal çıkarıldığı için favori–uzun atış yanlılığı toplamı bir
        miktar yukarı kaydırır.
      </div>
    </div>
  )
}
