import { Link } from 'react-router-dom'
import { adjustText, fmtOdd, fmtDateTime, fmtTime } from '../format.js'

/**
 * Biten maclarin tablosu - panonun tepesindeki ozet ve Sonuclar sayfasi ayni
 * bicimi kullanir.
 *
 * Her satirda macin nasil fiyatlandigi ve nasil bittigi yan yana: baslangic
 * 1X2, gercek skor, toplam gol, mac oncesi gol beklentisi, ILK TUTAN alt ve
 * ust cizgileri (oranlariyla) ve macta acilan EN BUYUK ust cizgisi.
 *
 * Ilk iki sutun sonuca gore secilir (tutan cizgilerin en dusukleri - oynanmis
 * olsa kazandiracak, toplama en yakin bacaklar); ucuncusu skordan bagimsiz,
 * kitabin teklif ettigi tavan. Sonuc o tavani da astiysa yesil + tik.
 *
 * Son sutun ORAN GOLU: ayni fiyata (ev/deplasman konumlari korunarak)
 * oynanmis ONCEKI maclarin gol ortalamasi. Yani "kitap bu maci boyle
 * fiyatladiysa gecmiste kac gol olmus". Toplam bu sayiyi astiysa yesil.
 *
 * Yesil tik: toplam gol beklentinin USTUNDE kalmis (beklenti alt sinir gibi
 * okunuyor - "en az bu kadar" bekleniyordu, oldu mu?).
 *
 * favorite=true (pano ozeti ve Sonuclar sayfasi): "En buyuk ust" yerine
 * "Favori / Surpriz" sutunu gelir ve tutan alt'in onune konur.
 *
 * Mac adinin yaninda oynandigi sezon yazar (her iki kullanimda da).
 *
 * detail=true (Sonuclar sayfasi): iki takimin ayri ayri mac oncesi gol
 * beklentisi. Takim beklentisi toplam beklentinin kesin
 * skor marketindeki paya gore bolunmesi (bkz. markets.goal_expectation);
 * takim o sayinin USTUNDE gol attiysa yesil - toplam sutunuyla ayni olcut.
 */

/* Baslangic orani dusuk olan taraf favori. Favori kazandiysa 'fav', oteki
   taraf kazandiysa 'surprise'; beraberlikte 'draw'. Oranlar esitse ya da
   eksikse favori yok -> null. */
function favoriteResult(m) {
  if (m.p1 == null || m.p2 == null || m.p1 === m.p2
      || m.score_home == null || m.score_away == null) return null
  if (m.score_home === m.score_away) return 'draw'
  const homeFav = m.p1 < m.p2
  const homeWon = m.score_home > m.score_away
  return homeFav === homeWon ? 'fav' : 'surprise'
}

export default function FinishedTable({ matches, showDate = false, mark = false,
                                        favorite = false, detail = false }) {
  /* mark=true -> tutan yesil-kalin + tik, tutmayan kirmizi + carpi.
     Sonuclar sayfasi da canli ozet de bu modda; mark=false yalnizca
     isaretsiz bir tablo isteyen bir cagiran olursa diye duruyor.

     `olculebilir` sart: mac oncesi arsivi olmayan maclarda hucreler bos
     kalir ve HICBIRI kirmizi isaretlenmez - "tutmadi" ile "olculemiyor"
     ayri seyler, ikisini ayni renge boyamak yaniltirdi. */
  const cls = (hit, olculebilir) =>
    (hit ? 'hit-ok' : (mark && olculebilir ? 'hit-no' : ''))
  const sign = (hit, olculebilir, ok, no) => {
    if (hit) return <span className="tick" title={ok}>✓</span>
    if (mark && olculebilir) return <span className="tick" title={no}>✗</span>
    return null
  }
  // Takimin kendi beklentisi: attigi gol ustundeyse tuttu.
  const teamExpect = (x, goals) => {
    const ok = x != null && goals != null && goals > x
    return (
      <td className={`num ${cls(ok, x != null)}`}>
        {x != null ? x.toFixed(2) : '—'}
        {sign(ok, x != null, 'takım beklentinin üstünde gol attı', 'takım beklentinin altında kaldı')}
      </td>
    )
  }
  return (
    <table>
      <thead>
        <tr>
          <th>{showDate ? 'Tarih' : 'Saat'}</th>
          <th>Maç</th>
          <th className="num">Skor</th><th className="num">Toplam</th>
          <th className="num" title="Ham beklentiden 0.5 çıkarılıp altındaki en yakın x.5'e yuvarlanmış değer">Beklenen</th>
          {detail && <>
            <th className="num" title="Ev sahibinin maç öncesi gol beklentisi — attığı gol bunu aştıysa yeşil">Ev bekl.</th>
            <th className="num" title="Deplasmanın maç öncesi gol beklentisi — attığı gol bunu aştıysa yeşil">Dep. bekl.</th>
          </>}
          <th className="num">1</th><th className="num">X</th><th className="num">2</th>
          {favorite && (
            <th className="num" title="Başlangıç oranı düşük olan takım kazandıysa Favori, diğer takım kazandıysa Sürpriz">
              Favori / Sürpriz</th>
          )}
          <th className="num" title="Tutan Alt çizgilerin EN DÜŞÜĞÜ — toplama en yakın üst sınır">
            İlk tutan alt</th>
          <th className="num" title="Tutan Üst çizgilerin EN DÜŞÜĞÜ — merdivenin tabanı">
            İlk tutan üst</th>
          {!favorite && (
            <th className="num" title="Maçta açılan en yüksek Üst çizgisi (skordan bağımsız) — tuttuysa yeşil">
              En büyük üst</th>
          )}
          <th className="num" title="Aynı oranla (ev/deplasman korunarak) oynanmış son maçların gol ortalamasından — tuttuysa yeşil">
            Oran gol</th>
        </tr>
      </thead>
      <tbody>
        {matches.map((m) => {
          const e = m.expect
          // Kitabin cizgileri elimizde mi - yoksa hicbir hucre "tutmadi"
          // diye isaretlenemez.
          const hasLines = m.book_over_last != null
          const topHit = m.total != null && hasLines && m.total > m.book_over_last
          const fav = favorite ? favoriteResult(m) : null
          return (
            <tr key={m.event_id} className={m.expect_hit ? 'hit-row' : undefined}>
              {/* Disaridan ice aktarilan kayitlarda mac oncesi tam market
                  seti yok - "Beklenen" ve tutan cizgiler bu satirlarda hep
                  bos kalir; nedeni tarihin ustunde yaziyor. */}
              <td className="muted" title={m.source
                ? `kaynak: ${m.source} - maç öncesi market arşivi yok`
                : undefined}>
                {showDate ? fmtDateTime(m.start_ts) : fmtTime(m.start_ts)}
              </td>

              <td>
                <Link to={`/mac/${m.event_id}`}>{m.home}
                  <span className="muted"> – </span>{m.away}</Link>
                {/* Macin oynandigi sezon. Toplayici maci baslamadan
                    yakaladiysa bilinir; ilk kez canliyken gorulen maclarda yok. */}
                {m.iteration != null && (
                  <span className="season-tag" title={`${m.iteration}. sezonda oynandı`}>
                    {m.iteration}. sezon</span>
                )}
              </td>
              <td className="num"><strong>{m.score_home} - {m.score_away}</strong></td>
              <td className="num"><strong>{m.total}</strong></td>
              {/* Parantez icindeki MAVI sayi kalibrasyon oncesi ham beklenti:
                  gosterilen deger ondan turetiliyor (ham − 0,5 → altindaki x.5). */}
              <td className={`num ${cls(m.expect_hit, e?.total != null)}`}
                  title={adjustText(e) || undefined}>
                {e?.total != null ? e.total.toFixed(2) : '—'}
                {e?.total_raw != null && (
                  <span className="adjust-note"> ({e.total_raw.toFixed(2)})</span>
                )}
                {sign(m.expect_hit, e?.total != null,
                      'toplam gol beklentinin üstünde', 'beklentinin altında kaldı')}
              </td>
              {detail && <>
                {teamExpect(e?.home, m.score_home)}
                {teamExpect(e?.away, m.score_away)}
              </>}
              <td className="num">{fmtOdd(m.p1)}</td>
              <td className="num">{fmtOdd(m.px)}</td>
              <td className="num">{fmtOdd(m.p2)}</td>
              {favorite && (
                <td className="num">
                  {fav === 'fav' && <span className="badge fav">Favori</span>}
                  {fav === 'surprise' && <span className="badge surprise">Sürpriz</span>}
                  {fav === 'draw' && <span className="muted">Beraberlik</span>}
                  {fav == null && '—'}
                </td>
              )}
              {/* Tutan iki uc: skora gore secilen, GERCEKTEN kazanmis en
                  dusuk Alt ve en dusuk Ust cizgileri, oranlariyla. Ikisi de
                  tanimi geregi tutmus - o yuzden ayrica yesille isaretlenmez,
                  bos kalmalari "hic tutan cizgi yok" demektir. */}
              <td className={`num ${cls(m.under_first != null, hasLines)}`}>
                {m.under_first ? <>Alt {m.under_first}
                  <span className="muted"> @{fmtOdd(m.under_first_odd)}</span></> : '—'}
                {sign(m.under_first != null, hasLines,
                      'bu alt çizgisi tuttu', 'hiçbir alt çizgisi tutmadı')}
              </td>
              <td className={`num ${cls(m.over_first != null, hasLines)}`}>
                {m.over_first ? <>Üst {m.over_first}
                  <span className="muted"> @{fmtOdd(m.over_first_odd)}</span></> : '—'}
                {sign(m.over_first != null, hasLines,
                      'bu üst çizgisi tuttu', 'hiçbir üst çizgisi tutmadı')}
              </td>
              {/* Macta acilan en yuksek Ust cizgisi - skordan BAGIMSIZ, yani
                  tutmamis da olabilir. Merdivenin tavani, en uzun oran;
                  tuttuysa yesil + tik. */}
              {!favorite && (
                <td className={`num ${cls(topHit, hasLines)}`}>
                  {m.book_over_last ? <>Üst {m.book_over_last}
                    <span className="muted"> @{fmtOdd(m.book_over_last_odd)}</span></> : '—'}
                  {sign(topHit, hasLines,
                        'en büyük üst de tuttu', 'en büyük üst tutmadı')}
                </td>
              )}
              {/* Oran golu: bu macin fiyatiyla, ayni dizilisle oynanmis
                  ONCEKI maclarin gol ortalamasi (kalibre edilmis). Yaninda
                  kac mactan geldigi duruyor - 3 macla 20 mac ayni sey degil. */}
              <td className={`num ${cls(m.odds_goal_hit, m.odds_goal != null)}`}
                  title={m.odds_goal_n
                    ? `aynı oranlı son ${m.odds_goal_n} maçın ortalamasından`
                    : 'aynı oranla oynanmış önceki maç yok'}>
                {m.odds_goal != null ? <>{m.odds_goal.toFixed(2)}
                  <span className="muted"> /{m.odds_goal_n}</span></> : '—'}
                {sign(m.odds_goal_hit, m.odds_goal != null,
                      'toplam oran golünün üstünde', 'oran golünün altında kaldı')}
              </td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}
