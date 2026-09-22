/**
 * Sonuclar sayfasinin tutma orani seridi.
 *
 * Uc olcut, ucu de AYNI filtrelenmis kume uzerinden ama FARKLI paydalarla -
 * her biri yalnizca olculebildigi maclarda sayilir:
 *
 *   Beklenti  toplam gol, mac oncesi beklentiyi asti mi (beklenti alt sinir
 *             gibi okunuyor). Payda: mac oncesi arsivi olan maclar.
 *   En buyuk toplam, macta ACILAN en yuksek Ust cizgisini de gecti mi
 *   ust       (tablodaki "En buyuk ust" sutunuyla ayni cizgi).
 *   Ilk ust   toplam, kitabin actigi en dusuk Ust cizgisini gecti mi (merdivenin
 *             tabani - cogu mac gecer, orani da o kadar kisadir).
 *
 * Yuzde tek basina gosterilmiyor: payda yaninda: kucuk ornekte %66 ile
 * 1000 macta %52 ayni sey degil.
 *
 * 'hit' filtresi seciliyken de kume ayni kalir (backend counts ile ayni
 * satirlari kullanir); aksi halde "Tuttu"ya basinca oran %100 gorunurdu.
 */
const TILES = [
  { key: 'expect', k: 'Beklenti tuttu',
    sub: 'toplam gol maç öncesi beklentiyi aştı',
    title: 'Beklenti alt sınır gibi okunuyor: "en az bu kadar gol" bekleniyordu, oldu mu?' },
  { key: 'over_last', k: 'En büyük üst tuttu',
    sub: 'toplam, maçta açılan en yüksek Üst çizgisini geçti',
    title: 'Maçta açılan en yüksek Üst çizgisi — merdivenin tavanı, en uzun oranlı bacak '
      + '(tablodaki "En büyük üst" sütunu)' },
  { key: 'over_first', k: 'İlk üst tuttu',
    sub: 'toplam, kitabın en düşük Üst çizgisini geçti',
    title: 'Kitabın açtığı en düşük Üst çizgisi — merdivenin tabanı, en kısa oranlı bacak' },
]

export default function HitRates({ rates, keys }) {
  if (!rates) return null
  // keys: yalnizca bu olcutler (pano kutusu ikisini gosteriyor).
  const shown = TILES.filter((t) => rates[t.key]?.n > 0
    && (!keys || keys.includes(t.key)))
  if (!shown.length) return null
  return (
    <div className="tiles">
      {shown.map((t) => {
        const r = rates[t.key]
        return (
          <div className="tile" key={t.key} title={t.title}>
            <div className="k">{t.k}</div>
            <div className="v">%{r.pct}</div>
            <div className="sub">
              {r.hit}/{r.n} maç · {t.sub}
            </div>
          </div>
        )
      })}
    </div>
  )
}
