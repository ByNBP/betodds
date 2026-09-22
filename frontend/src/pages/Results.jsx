import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api.js'
import { dayBefore, fmtDay } from '../format.js'
import useTitle from '../useTitle.js'
import FinishedTable from '../components/FinishedTable.jsx'
import LeagueSwitch from '../components/LeagueSwitch.jsx'
import HitRates from '../components/HitRates.jsx'
import FavCounts from '../components/FavCounts.jsx'
import Pager from '../components/Pager.jsx'

const PAGE = 100
// Disa aktarmada sunucudan tek seferde alinabilecek en buyuk sayfa (api le=200).
const EXPORT_PAGE = 200
const EMPTY_ODDS = { o1: '', ox: '', o2: '' }

/**
 * Sonuclar: biten maclar, panonun tepesindeki ozetle ayni bicimde.
 *
 * Suzme SUNUCUDA: takim/taraf/oran kosullari SQL'e giriyor, dolayisiyla
 * filtre daraldikca istek hizlaniyor ve ozet (mac sayisi, mac basi gol,
 * tuttu/tutmadi) her zaman SECIMIN TAMAMINI anlatiyor - ekrandaki 30
 * satiri degil.
 */
const FILTERS = [
  { key: '', label: 'Tümü', count: 'all' },
  { key: 'yes', label: 'Tuttu', count: 'hit' },
  { key: 'no', label: 'Tutmadı', count: 'miss' },
]

const SIDES = [
  { key: '', label: 'Her iki taraf' },
  { key: 'home', label: 'Evinde' },
  { key: 'away', label: 'Deplasmanda' },
]

/* Hazir tarih araliklari. Geri sayim ARSIVIN SON GUNUNDEN yapiliyor,
   takvimden bugunden degil: toplayici bir sure durmussa "son gun" bombos
   cikardi. `days: 0` = tarih suzgeci yok. */
const PRESETS = [
  { days: 0, label: 'Tümü' },
  { days: 1, label: 'Son gün' },
]

const filterLabel = (key) => FILTERS.find((f) => f.key === key)?.label ?? 'Tümü'
const sideLabel = (key) => SIDES.find((s) => s.key === key)?.label ?? ''

export default function Results({ champ, leagues, onChamp }) {
  useTitle('Sonuçlar')
  const [data, setData] = useState(null)
  const [offset, setOffset] = useState(0)
  const [hit, setHit] = useState('')
  const [team, setTeam] = useState('')
  const [side, setSide] = useState('')
  const [opp, setOpp] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  // Arsivin ilk/son gunu - takvim kutularinin sinirlari. AYRI tutuluyor:
  // her istekte data null'a dusuyor, span oradan okunsaydi tarih seridi
  // her tusta bir kaybolup gelirdi.
  const [span, setSpan] = useState(null)
  // Sayfa SON GUNLE aciliyor: once arsivin son gunu soruluyor, liste ancak
  // tarih kutulari dolduktan sonra cekiliyor - aksi halde tum arsiv bir
  // kez bosuna yuklenirdi.
  const [ready, setReady] = useState(false)
  const [odds, setOdds] = useState(EMPTY_ODDS)
  const [gap, setGap] = useState('0.25')
  const [teams, setTeams] = useState([])
  const [error, setError] = useState(null)
  const [printRows, setPrintRows] = useState(null)
  const [exporting, setExporting] = useState(false)
  // Disa aktarma hatasi AYRI tutuluyor: yuklenen liste duruyor, tum sayfayi
  // hata ekranina cevirmek yerine butonun yanina bir not dusuyoruz.
  const [exportError, setExportError] = useState(null)
  const listRef = useRef(null)

  const oddsOn = Boolean(odds.o1 || odds.ox || odds.o2)
  // Kutu bosaltilirsa ya da 0 girilirse sunucu 422 dondurur; varsayilana duseriz.
  const gapNum = Number(gap) > 0 ? gap : '0.25'

  // Tek sorgu nesnesi: hem listeyi hem PDF'i besler, ikisi ayrisamaz.
  const query = useMemo(() => ({
    champ_id: champ ?? '', hit,
    team: team.trim(), side, opp: opp.trim(),
    date_from: dateFrom, date_to: dateTo,
    o1: odds.o1, ox: odds.ox, o2: odds.o2,
    gap: oddsOn ? gapNum : '',
  }), [champ, hit, team, side, opp, dateFrom, dateTo,
       odds.o1, odds.ox, odds.o2, gapNum, oddsOn])

  // Filtre degisince listenin basina don - eski sayfa numarasi yeni kumede
  // bambaska bir yere denk gelirdi.
  useEffect(() => { setOffset(0) }, [query])

  // Takim kutularinin onerileri: ligin biten maclarinda gecen adlar.
  useEffect(() => {
    let alive = true
    api.teamStats(champ ?? '')
      .then((t) => alive && setTeams(
        t.map((x) => x.team).sort((a, b) => a.localeCompare(b, 'tr'))))
      .catch(() => alive && setTeams([]))
    return () => { alive = false }
  }, [champ])

  useEffect(() => {
    if (ready) return
    let alive = true
    api.resultsSpan(champ ?? '')
      .then((s) => {
        if (!alive) return
        if (s.last) { setSpan(s); setDateFrom(s.last); setDateTo(s.last) }
        setReady(true)
      })
      .catch((e) => alive && setError(e.message))
    return () => { alive = false }
  }, [ready, champ])

  useEffect(() => {
    if (!ready) return
    let alive = true
    setData(null)
    // Yazarken her tusa istek atmayalim.
    const t = setTimeout(() => {
      api.results({ ...query, limit: PAGE, offset })
        .then((d) => {
          if (!alive) return
          setData(d)
          setError(null)
          if (d.date_range?.first) setSpan(d.date_range)
        })
        .catch((e) => alive && setError(e.message))
    }, 250)
    return () => { alive = false; clearTimeout(t) }
  }, [query, offset, ready])

  /* PDF: ayri bir kutuphane YOK - filtrenin TUM satirlari cekilip yazdirma
     sayfasi olusturuluyor, tarayicinin yazdirma penceresinde hedef "PDF
     olarak kaydet" seciliyor. Boylece Turkce karakterler ve bicim
     ekrandakiyle birebir ayni kalir; cevrimdisi kuruluma yeni bagimlilik
     girmez. */
  const exportPdf = useCallback(async () => {
    setExporting(true)
    setExportError(null)
    try {
      const all = []
      // Sunucu 200'er satir veriyor; toplam bitene kadar sayfalari topla.
      // Guvenlik freni: arsiv beklenmedik bicimde buyurse dongude kalmayalim.
      for (let i = 0; i < 100; i++) {
        const d = await api.results({ ...query, limit: EXPORT_PAGE, offset: all.length })
        all.push(...d.matches)
        if (!d.matches.length || all.length >= d.total) break
      }
      setPrintRows(all)
    } catch (e) {
      setExportError(e.message)
    } finally {
      setExporting(false)
    }
  }, [query])

  // Sayfa DOM'a girdikten SONRA yazdirma penceresini ac; iki kare bekleniyor
  // cunku ilk karede tablo henuz yerlesmemis oluyor.
  useEffect(() => {
    if (!printRows) return
    document.body.classList.add('printing')
    const done = () => setPrintRows(null)
    window.addEventListener('afterprint', done)
    const frame = requestAnimationFrame(() =>
      requestAnimationFrame(() => window.print()))
    return () => {
      cancelAnimationFrame(frame)
      window.removeEventListener('afterprint', done)
      document.body.classList.remove('printing')
    }
  }, [printRows])

  const clearAll = () => {
    setTeam(''); setSide(''); setOpp(''); setOdds(EMPTY_ODDS); setGap('0.25')
    setDateFrom(''); setDateTo('')
  }

  // Hazir aralik: arsivin son gunune yaslanir, iki ucu da dahil.
  const applyPreset = (days) => {
    if (!days || !span?.last) { setDateFrom(''); setDateTo(''); return }
    setDateFrom(dayBefore(span.last, days - 1))
    setDateTo(span.last)
  }
  const presetOn = (days) => (days === 0
    ? !dateFrom && !dateTo
    : Boolean(span?.last) && dateTo === span.last
      && dateFrom === dayBefore(span.last, days - 1))
  const setOdd = (k) => (e) => setOdds((o) => ({ ...o, [k]: e.target.value }))

  // Etkin filtrelerin okunabilir listesi - hem ekranda hem PDF basliginda
  // ayni metin: ciktiya bakan biri hangi secimi gordugunu bilmeli.
  const active = []
  if (team.trim()) {
    active.push(side ? `${team.trim()} (${sideLabel(side).toLowerCase()})`
      : `Takım: ${team.trim()}`)
  } else if (side) {
    active.push(`Taraf: ${sideLabel(side)}`)
  }
  if (opp.trim()) active.push(`Rakip: ${opp.trim()}`)
  if (dateFrom && dateTo) {
    active.push(dateFrom === dateTo ? `Tarih: ${fmtDay(dateFrom)}`
      : `Tarih: ${fmtDay(dateFrom)} – ${fmtDay(dateTo)}`)
  } else if (dateFrom) {
    active.push(`Tarih: ${fmtDay(dateFrom)} ve sonrası`)
  } else if (dateTo) {
    active.push(`Tarih: ${fmtDay(dateTo)} ve öncesi`)
  }
  for (const [k, lbl] of [['o1', '1'], ['ox', 'X'], ['o2', '2']]) {
    if (odds[k]) active.push(`${lbl} = ${odds[k]} ±${gapNum}`)
  }
  const anyFilter = active.length > 0

  if (error) return <div className="error">Sonuçlar alınamadı: {error}</div>

  const rows = data?.matches || []
  const total = data?.total ?? 0
  const from = total ? offset + 1 : 0
  const to = offset + rows.length
  const league = leagues?.find((l) => l.champ_id === champ) || null

  return (
    <>
      <LeagueSwitch leagues={leagues} champ={champ} onChange={onChamp} />

      {/* Tarih araligi EN USTTE: "hangi gunlere bakiyorum" sorusu takim ya da
          oran suzgecinden once cevaplanmali. Iki uc da DAHIL - 5 Eylul'den
          5 Eylul'e secmek o gunun tamamini verir. */}
      <div className="controls date-filter">
        <span className="muted">Tarih:</span>
        <input type="date" value={dateFrom} aria-label="Başlangıç günü"
          min={span?.first} max={dateTo || span?.last}
          onChange={(e) => setDateFrom(e.target.value)}
          title="Başlangıç günü (bu gün dahil)" />
        <span className="muted">–</span>
        <input type="date" value={dateTo} aria-label="Bitiş günü"
          min={dateFrom || span?.first} max={span?.last}
          onChange={(e) => setDateTo(e.target.value)}
          title="Bitiş günü (bu gün dahil)" />
        {PRESETS.map((p) => (
          <button key={p.days} className={presetOn(p.days) ? 'primary' : ''}
            disabled={p.days > 0 && !span?.last}
            onClick={() => applyPreset(p.days)}>{p.label}</button>
        ))}
        {span?.first && (
          <span className="muted" style={{ alignSelf: 'center' }}>
            arşiv: {fmtDay(span.first)} – {fmtDay(span.last)}
          </span>
        )}
      </div>

      <datalist id="results-teams">
        {teams.map((t) => <option key={t} value={t} />)}
      </datalist>

      {/* Takim aramasi. Taraf ayri bir kutu: "Real Madrid" yazip "Evinde"
          demek iki ayri metin kutusu doldurmaktan kisa, ve "her iki taraf"
          secenegini de koruyor - iki kutulu tasarimda o secenek kaybolurdu. */}
      <div className="controls">
        <input list="results-teams" placeholder="Takım ara…" value={team}
          onChange={(e) => setTeam(e.target.value)} />
        <select value={side} onChange={(e) => setSide(e.target.value)}
          title="Takımın hangi tarafta oynadığı">
          {SIDES.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
        </select>
        <input list="results-teams" placeholder="Rakip (isteğe bağlı)…" value={opp}
          onChange={(e) => setOpp(e.target.value)}
          title="Karşı taraftaki takım. Taraf seçilmemişse eşleşme iki yönlüdür." />
        {anyFilter && <button onClick={clearAll}>Filtreyi temizle</button>}
      </div>

      <div className="controls odds-filter">
        <span className="muted">Maç öncesi oran:</span>
        <input type="number" step="0.01" min="1" placeholder="1"
          value={odds.o1} onChange={setOdd('o1')} title="Ev sahibi oranı" />
        <input type="number" step="0.01" min="1" placeholder="X"
          value={odds.ox} onChange={setOdd('ox')} title="Beraberlik oranı" />
        <input type="number" step="0.01" min="1" placeholder="2"
          value={odds.o2} onChange={setOdd('o2')} title="Deplasman oranı" />
        <span className="muted">± </span>
        <input type="number" step="0.05" min="0.01" value={gap}
          onChange={(e) => setGap(e.target.value)} title="Tolerans" />
        {oddsOn && (
          <span className="muted" style={{ alignSelf: 'center' }}>
            girilen her oran için ±{gapNum}
          </span>
        )}
      </div>

      {/* Tuttu = toplam gol maç öncesi beklentiyi aştı. Beklentisi olmayan
          maçlar iki filtreye de girmez, soru onlar için cevaplanamıyor.
          Sayaçlar yukarıdaki filtrelerin daralttığı kümeyi anlatır. */}
      <div className="controls">
        {FILTERS.map((f) => (
          <button key={f.key} className={hit === f.key ? 'primary' : ''}
            onClick={() => setHit(f.key)}>
            {f.label}
            {data?.counts && <span className="muted"> {data.counts[f.count]}</span>}
          </button>
        ))}
        {data?.counts?.no_expect > 0 && (
          <span className="muted" style={{ alignSelf: 'center' }}>
            {data.counts.no_expect} maçta maç öncesi arşiv yok, ölçülemiyor
          </span>
        )}
      </div>

      {/* Tutma oranlari: sayfadaki 50 satirin degil, FILTRENIN TUMUNUN
          uzerinden. Tabloya bakmadan once "bu secim ne kadar tutuyor"
          sorusunun cevabi burada. */}
      <HitRates rates={data?.rates} />

      {/* Favori / surpriz kazanan: ayni kume (hit filtresinden once). */}
      {data?.favorite && (
        <div className="panel" style={{ marginBottom: 16 }}>
          <FavCounts fav={data.favorite} />
        </div>
      )}

      <div className="panel scroll-x" ref={listRef}>
        <div className="chart-head">
          <h2>Sonuçlar</h2>
          {data && (
            <span className="muted">
              {from}–{to} / {total} maç
              {data.avg_goals != null && <> · maç başı <strong>{data.avg_goals}</strong> gol</>}
              {!hit && data.counts && data.counts.hit + data.counts.miss > 0 && (
                <> · <strong>{data.counts.hit}</strong>/{data.counts.hit + data.counts.miss} maçta
                  toplam beklentinin üstünde</>
              )}
              {anyFilter && <> · {active.join(' · ')}</>}
            </span>
          )}
          {/* Yazdirma penceresinde hedef olarak "PDF olarak kaydet" secilir -
              buton bunu baslik metninde de soyluyor. */}
          <button onClick={exportPdf} disabled={exporting || !total}
            title="Yazdırma penceresinde Hedef → 'PDF olarak kaydet' seçin">
            {exporting ? 'Hazırlanıyor…' : 'PDF'}
          </button>
          {exportError && (
            <span className="muted">PDF hazırlanamadı: {exportError}</span>
          )}
        </div>

        {!data ? <div className="empty">Yükleniyor…</div>
          : rows.length === 0 ? <div className="empty">Bu filtreye uyan maç yok.</div>
          : <FinishedTable matches={rows} showDate mark favorite />}
      </div>

      {/* Sayfa numaralari: 50 sayfalik arsivde ileri/geri ile gezmek
          iskence. Numaraya basinca listenin basina donuyoruz - aksi halde
          yeni sayfa tablonun ortasindan aciliyordu.
          scrollIntoView isaretli: duman testlerinin jsdom'unda yok. */}
      <Pager page={Math.floor(offset / PAGE) + 1}
        pages={Math.max(1, Math.ceil(total / PAGE))}
        onPage={(p) => {
          setOffset((p - 1) * PAGE)
          listRef.current?.scrollIntoView?.({ block: 'start' })
        }} />

      {/* Yalnizca yazdirmada gorunur: ekrandaki sayfa degil, filtrenin TUM
          satirlari. Sayfa boyutu burada veriliyor ki uygulamanin diger
          sayfalarindaki Ctrl+P davranisi degismesin. */}
      {printRows && (
        <div className="print-sheet">
          <style>{'@page { size: A4 landscape; margin: 12mm; }'}</style>
          <div className="print-head">
            <h1>BetOdds · Sonuçlar</h1>
            <div className="print-meta">
              <span>{league ? league.name : 'Tüm ligler'}</span>
              {active.map((a) => <span key={a}>{a}</span>)}
              <span>Beklenti: {filterLabel(hit)}</span>
              {data?.favorite && (
                <span>
                  Favori {data.favorite.favorite} · Sürpriz {data.favorite.surprise}
                  {' '}· beraberlik {data.favorite.draw}
                </span>
              )}
              <span>{printRows.length} maç</span>
              {data?.avg_goals != null && <span>maç başı {data.avg_goals} gol</span>}
              {!hit && data?.counts && data.counts.hit + data.counts.miss > 0 && (
                <span>
                  {data.counts.hit}/{data.counts.hit + data.counts.miss} maçta
                  {' '}toplam beklentinin üstünde
                </span>
              )}
              <span>{new Date().toLocaleString('tr-TR')}</span>
            </div>
          </div>
          <FinishedTable matches={printRows} showDate mark favorite />
        </div>
      )}
    </>
  )
}
