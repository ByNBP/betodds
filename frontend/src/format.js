// Ortak bicimlendiriciler.

export const fmtTime = (ts) =>
  ts ? new Date(ts * 1000).toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' }) : '—'

export const fmtDateTime = (ts) =>
  ts ? new Date(ts * 1000).toLocaleString('tr-TR', {
    day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
  }) : '—'

/* Gun bicimleri. Tarih suzgeci gunlerle konusuyor ('2026-09-09'), zaman
   damgasiyla degil: bir gunun tamami yerel saate gore secilir. */

// Date -> 'YYYY-AA-GG', YEREL gune gore. toISOString() UTC'ye cevirdigi icin
// dogu yarikuresinde gunu bir geri kaydiriyordu - o yuzden elle kuruluyor.
export const isoDay = (d) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`

// 'YYYY-AA-GG' -> '09.09.2026'
export const fmtDay = (iso) =>
  iso ? new Date(`${iso}T00:00:00`).toLocaleDateString('tr-TR') : ''

// Gun kaydirma: iso'dan `days` gun geriye (0 = ayni gun).
export const dayBefore = (iso, days) => {
  const d = new Date(`${iso}T00:00:00`)
  d.setDate(d.getDate() - days)
  return isoDay(d)
}

export const fmtOdd = (v) => (v === null || v === undefined ? '—' : Number(v).toFixed(2))

export const scoreText = (m) =>
  m.score_home === null || m.score_home === undefined ? 'vs' : `${m.score_home} - ${m.score_away}`

// Baslangica kalan/gecen sure. Kartlarda backend'in status_text'i yerine bunu
// kullaniyoruz: status_text son poll aninda dondugu icin toplayici durdugunda
// saatler sonra hala "3 dakika icinde basliyor" demeye devam eder.
const durText = (sec) => {
  const dk = Math.round(sec / 60)
  if (dk < 60) return `${dk} dakika`
  const sa = Math.floor(dk / 60)
  if (sa >= 24) return `${Math.floor(sa / 24)} gün`
  return dk % 60 ? `${sa} sa ${dk % 60} dk` : `${sa} saat`
}

export const startText = (m) => {
  if (m.status === 'live') return m.status_text || null   // canli dakika feed'den
  if (m.status !== 'scheduled' || !m.start_ts) return null
  const diff = m.start_ts - Date.now() / 1000
  if (diff > 0) return diff < 60 ? 'birazdan' : `${durText(diff)} içinde`
  return `${durText(-diff)} önce başlamalıydı`
}

export const STATUS_LABEL = {
  scheduled: 'Başlamadı',
  live: 'Canlı',
  finished: 'Bitti',
}

// Oranin ima ettigi olasilik (marj dahil) - oran hareketini yorumlamak icin.
export const impliedPct = (odd) => (odd ? (100 / odd).toFixed(1) + '%' : '—')

/**
 * Beklenen gol kalibrasyonunun islemini okunur hale getirir:
 *   14.85 -> "14.85 − 0.5 → 14.5"
 *
 * Ham deger yoksa (eski kayit) null doner; cagiran yer islemi hic gostermez.
 */
export function adjustText(e) {
  if (!e || e.total_raw == null || e.total == null) return null
  const off = e.adjust?.offset ?? 0.5
  // Yuvarlama tam sayilara degil yalnizca yarimlara ve ASAGI dogru: kitabin
  // Toplam Gol cizgileri her zaman x.5, beklenti de bir cizgiye denk gelmeli
  // ve o cizginin altinda kalmali (alt sinir gibi okunuyor).
  return `${e.total_raw.toFixed(2)} − ${off} → altındaki x.5 → ${e.total.toFixed(2)}`
    + ` → ${fmtGoal(e.total)}`
}

/**
 * Istatistik gol sayisi ekranda EN YAKIN TAM SAYI olarak yazilir (5.50 -> 6).
 * Kalibre deger hep x.5 oldugu icin bu, "toplam > 5.5" olcutunu "toplam >= 6"
 * diye okumakla ayni: tuttu/tutmadi hesabi degismiyor, yalnizca gosterim.
 */
export const fmtGoal = (v) => (v == null ? '—' : String(Math.round(v)))

/**
 * "Favori maç" etiketi - uc kosulun HEPSI:
 *   1. Favori orani (mac oncesi 1 ve 2'den dusugu) 1.80'in USTUNDE ve
 *      1.95'in ALTINDA (iki sinir da haric),
 *   2. iki takimin beklenen golu (kartta yazan, kalibre) arasindaki fark
 *      0.50'nin ALTINDA,
 *   3. ham beklenti (kalibrasyon oncesi, "parantez ici") >= 7.50.
 * Mac oncesi oran yoksa (p1/p2) o anki 1X2'ye bakilir - baslamamis macta
 * ikisi ayni sey. Veri eksikse etiket yok.
 */
export const FAV_MATCH = { minFavOdd: 1.80, maxFavOdd: 1.95, maxGoalGap: 0.50, minRaw: 7.50 }

export function isFavoriteMatch(m) {
  const e = m.expect
  const o1 = m.p1 ?? m.o1
  const o2 = m.p2 ?? m.o2
  if (!e || o1 == null || o2 == null || e.home == null || e.away == null
      || e.total_raw == null) return false
  const fav = Math.min(o1, o2)
  return fav > FAV_MATCH.minFavOdd && fav < FAV_MATCH.maxFavOdd
    && Math.abs(e.home - e.away) < FAV_MATCH.maxGoalGap
    && e.total_raw >= FAV_MATCH.minRaw
}
