import { adjustText, fmtDateTime, fmtOdd } from '../format.js'

/**
 * Mac kartinin yanindaki gecmis kutusu - iki tablo:
 *
 *   1) ayni iki takimin BIZIM arsivimizdeki maclari (oranlariyla)
 *   2) ayni iki takimin son N sezondaki maclari (eventsstat capraz sonuc
 *      tablosundan - yalnizca skor, oran yok)
 *   3) bu macin takimlarindan YALNIZCA BIRININ oynadigi ve o takimin ayni
 *      oranla fiyatlandigi maclar (eslesen takimin orani vurgulanir)
 *   4) ORAN GOLU: takim gozetmeksizin, ayni fiyata ve ayni dizilisle
 *      oynanmis onceki maclar - ortalamasi bu macin gol tahmini
 *
 * Oranlar her zaman mac ONCESI referans setinden; canli oran mac ici hareketi
 * tasidigi icin gecmisle kiyaslanamaz.
 *
 * Tutan cizgilerden ikisi gosteriliyor:
 *   Son alt = skoru gecen en dusuk alt (skora en yakin alt)
 *   Ilk ust = kitabin actigi en dusuk ust (tutan ustlerin tabani)
 */
// Lig sirasi kartlardakiyle AYNI bicimde (.team-pos): ayni bilgi iki yerde
// iki turlu gorunmesin. Ustsimge (<sup>) birakildi - kucuk, sonuk ve satir
// yuksekligini bozan bir bicimdi.
function Pos({ n, current }) {
  if (!n) return null
  return (
    <span className="team-pos"
          title={current ? 'güncel sezon sırası' : 'o sezondaki sıra'}>
      {n}.{current ? '*' : ''}
    </span>
  )
}

function Table({ rows }) {
  return (
    <table>
      <thead>
        <tr>
          <th>Tarih</th><th>Maç</th><th className="num">Skor</th>
          <th className="num">1</th><th className="num">X</th><th className="num">2</th>
          <th className="num">Son alt</th><th className="num">İlk üst</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.event_id}>
            <td className="muted">{fmtDateTime(r.start_ts)}</td>
            <td>
              <span className={r.team === r.home ? 'ours' : ''}>
                {r.home}<Pos n={r.home_pos} current={r.pos_current} />
              </span>
              <span className="muted"> – </span>
              <span className={r.team === r.away ? 'ours' : ''}>
                {r.away}<Pos n={r.away_pos} current={r.pos_current} />
              </span>
            </td>
            <td className="num"><strong>{r.score_home} - {r.score_away}</strong></td>
            <td className={`num ${r.hit_1 ? 'hit' : ''}`}>{fmtOdd(r.p1)}</td>
            <td className="num">{fmtOdd(r.px)}</td>
            <td className={`num ${r.hit_2 ? 'hit' : ''}`}>{fmtOdd(r.p2)}</td>
            <td className="num">
              {r.under_first ? <>Alt {r.under_first}
                <span className="muted"> @{fmtOdd(r.under_first_odd)}</span></> : '—'}
            </td>
            <td className="num">
              {r.over_first ? <>Üst {r.over_first}
                <span className="muted"> @{fmtOdd(r.over_first_odd)}</span></> : '—'}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function Summary({ block, home, away }) {
  return (
    <div className="h2h-sum">
      maç başı <strong>{block.avg_total}</strong> gol
      {block.avg_home !== undefined && (
        <span className="muted"> · {home} {block.avg_home} – {block.avg_away} {away}</span>
      )}
    </div>
  )
}

/** Sezon capraz tablosundan gelen maclar: oran yok, yalnizca skor. */
function SeasonTable({ rows, home }) {
  return (
    <table>
      <thead>
        <tr>
          <th className="num">Sezon</th><th>Maç</th>
          <th className="num">Skor</th><th className="num">Toplam</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={`${r.iteration}-${r.home}-${i}`}>
            <td className="num muted">{r.iteration}</td>
            <td>
              <span className={r.home === home ? 'ours' : ''}>{r.home}</span>
              <span className="muted"> – </span>
              <span className={r.away === home ? 'ours' : ''}>{r.away}</span>
            </td>
            <td className="num"><strong>{r.score_home} - {r.score_away}</strong></td>
            <td className="num">{r.total}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

/**
 * Oran golu: bu macin FIYATIYLA oynanmis onceki maclarda kac gol olmus.
 *
 * Eslesme ev/deplasman konumlari korunarak yapilir - ev ayagi ev ayagiyla,
 * deplasman ayagi deplasman ayagiyla. Takim onemli degil; soru "kitap bir
 * maci boyle fiyatladiginda ne oluyor".
 *
 * Ortalamanin kendisi degil, uygulamanin kalibrasyonundan gecmis hali
 * gosteriliyor (ortalama - 0.5, altindaki x.5): boylece dogrudan bir Alt/Ust
 * cizgisiyle karsilastirilabiliyor. Ham ortalama yaninda duruyor.
 *
 * Ornek sayisi HER YERDE yazili: 3 macla 20 mac ayni sey degil.
 */
function OddsGoals({ og, home, away }) {
  if (!og || !og.n) {
    return (
      <div className="empty" style={{ padding: '10px 8px' }}>
        Bu oranla (±{og?.gap ?? 0.02}) daha önce oynanmış maç arşivde yok.
      </div>
    )
  }
  return (
    <>
      <div className="chart-sub" style={{ marginBottom: 8 }}>
        ev/deplasman konumları korunarak aynı oranla oynanmış son {og.n} maç ·
        ortalama <strong>{og.avg_home}</strong> – <strong>{og.avg_away}</strong>
        {' '}= <strong>{og.avg_total}</strong> gol
        {og.n < og.limit ? ` · arşivde bu kadarı var (en fazla ${og.limit})` : ''}
      </div>
      <table>
        <thead>
          <tr>
            <th>Tarih</th><th>Maç</th>
            <th className="num">1</th><th className="num">2</th>
            <th className="num" title={home}>Ev</th>
            <th className="num" title={away}>Dep</th>
            <th className="num">Toplam</th>
          </tr>
        </thead>
        <tbody>
          {og.matches.map((r) => (
            <tr key={r.event_id}>
              <td className="muted">{fmtDateTime(r.start_ts)}</td>
              <td>{r.home}<span className="muted"> – </span>{r.away}</td>
              <td className="num">{fmtOdd(r.p1)}</td>
              <td className="num">{fmtOdd(r.p2)}</td>
              <td className="num">{r.score_home}</td>
              <td className="num">{r.score_away}</td>
              <td className="num"><strong>{r.total}</strong></td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr>
            <td><strong>Ortalama</strong></td>
            <td className="muted">
              {og.n} maçın ortalaması
              {og.matches.length < og.n ? ` (ilk ${og.matches.length} tanesi listelendi)` : ''}
            </td>
            <td /><td />
            <td className="num"><strong>{og.avg_home}</strong></td>
            <td className="num"><strong>{og.avg_away}</strong></td>
            <td className="num"><strong>{og.avg_total}</strong></td>
          </tr>
        </tfoot>
      </table>
    </>
  )
}

export default function MatchHistory({ h2h, home, away, expect }) {
  const past = h2h?.matches || []
  const same = h2h?.same_odds
  const sameRows = same?.matches || []
  const seas = h2h?.seasons
  const seasRows = seas?.matches || []
  const oddsGoal = h2h?.odds_goal

  const anyCurrent = [...past, ...sameRows]
    .some((r) => r.pos_current && (r.home_pos || r.away_pos))

  return (
    <div className="panel h2h scroll-x">
      {/* Ilk basligin sag ucunda macin kendi beklentisi: asagidaki tablolar
          hep onunla karsilastirmak icin okunuyor, ayni satirda dursun. */}
      <div className="h2h-title">
        <h3>Geçmiş karşılaşma{past.length ? ` (${h2h.n})` : ''}</h3>
        {expect?.total != null && (
          <h3 className="h2h-expect">
            Beklenen gol <strong>{expect.total.toFixed(2)}</strong>
            {/* Mavi: kalibrasyon oncesi ham deger (bkz. format.adjustText). */}
            {expect.total_raw != null && (
              <span className="adjust-note" title={adjustText(expect) || undefined}>
                {' '}({expect.total_raw.toFixed(2)})
              </span>
            )}
            {expect.home != null && (
              <span className="muted"> · {expect.home.toFixed(2)} – {expect.away.toFixed(2)}</span>
            )}
          </h3>
        )}
      </div>
      {past.length ? (
        <>
          <Summary block={h2h} home={home} away={away} />
          <Table rows={past} />
        </>
      ) : (
        <div className="empty" style={{ padding: '10px 8px' }}>
          Bu eşleşme arşivde ilk kez.
        </div>
      )}

      <h3 style={{ marginTop: 18 }}>
        Aynı oranlı maçlar{sameRows.length ? ` (${same.n})` : ''}
        {same?.gap
          ? <span className="muted"> · tek takım · ±{same.gap}
              {same.min_legs ? ` · en az ${same.min_legs}/3 ayak` : ''} · en yeni {same.limit}</span>
          : null}
      </h3>
      {sameRows.length ? (
        <>
          <Summary block={same} home={home} away={away} />
          <Table rows={sameRows} />
        </>
      ) : (
        <div className="empty" style={{ padding: '10px 8px' }}>
          {same?.ref
            ? `${home} ${same.ref.p1} ya da ${away} ${same.ref.p2} oranıyla oynadığı`
              + ' başka maç arşivde yok.'
            : 'Maç öncesi 1X2 oranı arşivde yok.'}
        </div>
      )}

      <h3 style={{ marginTop: 18 }}>
        Oran golü
        {oddsGoal?.n
          ? <span className="muted"> · son {oddsGoal.n} maç beklenen gol{' '}
              <strong>{oddsGoal.total}</strong></span>
          : null}
      </h3>
      <OddsGoals og={oddsGoal} home={home} away={away} />

      <h3 style={{ marginTop: 18 }}>
        Son {seas?.seasons?.length || 0} sezon{seasRows.length ? ` (${seas.n})` : ''}
        {seas?.seasons?.length
          ? <span className="muted"> · sezon {seas.seasons[seas.seasons.length - 1]}–{seas.seasons[0]}</span>
          : null}
      </h3>
      {seasRows.length ? (
        <>
          <Summary block={seas} home={home} away={away} />
          <SeasonTable rows={seasRows} home={home} />
        </>
      ) : (
        <div className="empty" style={{ padding: '10px 8px' }}>
          {seas?.seasons?.length
            ? 'Bu iki takım son sezonlarda karşılaşmamış.'
            : 'Sezon maçları henüz çekilmedi.'}
        </div>
      )}

      <div className="h2h-note muted">
        Oranlar maç öncesi referans setinden. <strong>Son alt</strong> skoru geçen
        en düşük alt, <strong>ilk üst</strong> kitabın açtığı en düşük üst.{' '}
        <strong>Son sezonlar</strong> sitenin sezon özetinden gelir (çapraz sonuç
        tablosu); orada oran yok, yalnızca skor.{' '}
        <strong>Oran golü</strong>: bu maçın fiyatıyla — ev/deplasman
        konumları korunarak, 1 ve 2 ayakları ±{oddsGoal?.gap ?? 0.02} içinde —
        oynanmış <em>önceki</em> maçların gol ortalaması. Sonradan oynanmış
        maçlar sayılmaz; aksi halde bitmiş bir maçın tahminine kendi geleceği
        karışırdı. Başlıktaki değer ortalamanın kalibre edilmiş hâlidir
        (ortalama − 0,5, altındaki x.5), böylece doğrudan bir Alt/Üst
        çizgisiyle karşılaştırılabilir.{' '}
        <strong>Aynı oranlı maçlar</strong>: bu maçın iki takımından yalnızca
        birinin oynadığı ve o takımın aynı oranla fiyatlandığı maçlar — takım
        evde de deplasmanda da olabilir, oran kendi ayağından okunur ve
        vurgulanır. Takımın kendi ayağı tek başına yetmez: 1/X/2 ayaklarından
        en az {same?.min_legs ?? 2} tanesi de aynı toleransa girmeli. Ayaklar
        takımın bakış açısıyla hizalanır (kendi oranı, beraberlik, rakip
        oranı), yani takım geçmişte diğer tarafta oynadıysa 1 ile 2 yer
        değiştirir.
        {anyCurrent && ' Yıldızlı sıralar güncel sezon tablosundan (o maçın sezonu kayıtlı değil).'}
      </div>
    </div>
  )
}
