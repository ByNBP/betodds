/**
 * Sonuclar sayfasinin tarih suzgeci ve numarali sayfalamasi - gercek render
 * ve gercek tiklamalar uzerinden.
 *
 * Sayfa SON GUNLE aciliyor; sayfalama kontrolleri once "Tumu"ne basip tum
 * arsivde yapiliyor.
 *
 * Ikisi de yalnizca ETKILESIMDE ortaya cikiyor: ilk yukleme dogru gorunup
 * "3. sayfa" bambaska bir dilim getirebilir ya da suzgec degisince eski
 * sayfa numarasi yeni kumede askida kalabilir. smoke-routes.mjs sayfayi
 * yalnizca aciyor, o yuzden bu kontroller ayri.
 *
 * Kullanim:  SMOKE_URL=http://127.0.0.1:8000/ node scripts/smoke-results.mjs
 */
import * as esbuild from 'esbuild'
import { JSDOM, VirtualConsole } from 'jsdom'

const base = process.env.SMOKE_URL || 'http://127.0.0.1:8000/'
const built = await esbuild.build({
  entryPoints: ['src/main.jsx'], bundle: true, write: false, format: 'iife',
  platform: 'browser', jsx: 'automatic',
  loader: { '.js': 'jsx', '.jsx': 'jsx', '.css': 'empty' },
  define: { 'process.env.NODE_ENV': '"development"' }, logLevel: 'silent',
})
const bundle = built.outputFiles[0].text

const errors = []
const vc = new VirtualConsole()
vc.on('jsdomError', (e) => errors.push('jsdomError: ' + e.message))
vc.on('error', (...a) => errors.push('console.error: ' + a.join(' ')))
const dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>', {
  url: new URL('/sonuclar', base).toString(),
  runScripts: 'dangerously', pretendToBeVisual: true, virtualConsole: vc,
})
const { window } = dom
window.EventSource = class { constructor() { this.readyState = 0 } close() {} }
window.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} }
const nodeFetch = globalThis.fetch
window.fetch = (i, init) => nodeFetch(
  typeof i === 'string' && i.startsWith('/') ? new URL(i, base).toString() : i, init)
window.eval(bundle)

const doc = window.document
const wait = (ms) => new Promise((r) => setTimeout(r, ms))
const rows = () => doc.querySelectorAll('table tbody tr').length
const head = () => (doc.querySelector('table tbody tr')?.textContent || '').replace(/\s+/g, ' ').trim()
const pagerBtns = () => [...doc.querySelectorAll('.pager button')].map((b) => b.textContent.trim())
const summary = () => (doc.querySelector('.chart-head .muted')?.textContent || '').replace(/\s+/g, ' ').trim()
let failed = 0
const check = (n, ok, extra = '') => { console.log(`  ${ok ? '✓' : '✗'} ${n}${extra ? '  ' + extra : ''}`); if (!ok) failed++ }
const click = async (el, ms = 1200) => { el.dispatchEvent(new window.MouseEvent('click', { bubbles: true })); await wait(ms) }

const totalOf = (s) => Number((s.match(/\/ (\d+) maç/) || [])[1])
const preset = (l) => [...doc.querySelectorAll('.date-filter button')].find((b) => b.textContent.trim() === l)
const headers = () => [...doc.querySelectorAll('table thead th')].map((th) => th.textContent.trim())

await wait(3000)
// --- acilis: son gun ----------------------------------------------------
const sonGun = preset('Son gün')
const tumu = preset('Tümü')
check('tarih kutuları var', doc.querySelectorAll('.date-filter input[type=date]').length === 2)
check('hazır aralıklar yalnızca Tümü + Son gün',
  [...doc.querySelectorAll('.date-filter button')].map((b) => b.textContent.trim()).join('|') === 'Tümü|Son gün')
check('açılışta "Son gün" işaretli', !!sonGun?.className.includes('primary'))
check('açılışta özette tarih yazılı', /Tarih: \d\d\.\d\d\.\d{4}/.test(summary()), summary().slice(-40))
const dayTotal = totalOf(summary())
check('açılışta son günün maçları var', dayTotal > 0, `${dayTotal} maç`)
check('Favori / Sürpriz sütunu var, En büyük üst yok',
  headers().includes('Favori / Sürpriz') && !headers().includes('En büyük üst'))
const hi = headers()
check('Favori / Sürpriz, İlk tutan alt\'ın hemen önünde',
  hi.indexOf('Favori / Sürpriz') + 1 === hi.indexOf('İlk tutan alt'))
const favCells = [...doc.querySelectorAll('table tbody tr')].map((tr) =>
  tr.children[hi.indexOf('Favori / Sürpriz')]?.textContent.trim())
check('hücreler Favori/Sürpriz/Beraberlik/—',
  favCells.length > 0 && favCells.every((t) => ['Favori', 'Sürpriz', 'Beraberlik', '—'].includes(t)),
  [...new Set(favCells)].join(','))

// --- Tumu: sayfalama tum arsivde ------------------------------------------
await click(tumu, 4500)
const allTotal = totalOf(summary())
check('"Tümü" son günden geniş', allTotal > dayTotal, `${dayTotal} -> ${allTotal}`)
check('30 satır listeleniyor', rows() === 30, `satır:${rows()}`)
check('arşiv aralığı yazılı', /arşiv: \d\d\.\d\d\.\d{4} – \d\d\.\d\d\.\d{4}/.test(
  doc.querySelector('.date-filter')?.textContent || ''), doc.querySelector('.date-filter')?.textContent.match(/arşiv:.*/)?.[0])

const p1 = pagerBtns()
console.log('  pager:', p1.join(' '))
check('sayfa numaraları var', p1.includes('1') && p1.includes('2') && p1.includes('3'))
check('1. sayfa işaretli', doc.querySelector('.pager button.primary')?.textContent.trim() === '1')
check('elips ile kısalıyor', doc.querySelectorAll('.pager-gap').length >= 1)
check('sayfaya git kutusu var', !!doc.querySelector('.pager-jump input'))

// --- 3. sayfaya dogrudan atla -------------------------------------------
const first = head()
const btn3 = [...doc.querySelectorAll('.pager button')].find((b) => b.textContent.trim() === '3')
await click(btn3, 4500)
check('3. sayfaya atladı', doc.querySelector('.pager button.primary')?.textContent.trim() === '3')
check('satırlar değişti', head() !== first && rows() === 30)
check('özet 61–90 diyor', summary().startsWith('61–90'), summary().slice(0, 40))

// --- sayfaya git kutusu --------------------------------------------------
const jump = doc.querySelector('.pager-jump input')
const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set
setter.call(jump, '12')
jump.dispatchEvent(new window.Event('input', { bubbles: true }))
await wait(60)
await click(doc.querySelector('.pager-jump button[type=submit]'), 4500)
check('12. sayfaya gitti', doc.querySelector('.pager button.primary')?.textContent.trim() === '12')
check('özet 331–360 diyor', summary().startsWith('331–360'), summary().slice(0, 40))

// --- tarih suzgeci -------------------------------------------------------
await click(sonGun, 1800)
const dayTotal2 = totalOf(summary())
// Toplayici calisiyor: arada yeni mac bitmis olabilir, azalmaz ama artabilir.
check('son gün süzgeci daralttı', dayTotal2 >= dayTotal && dayTotal2 < allTotal, `${allTotal} -> ${dayTotal2}`)
// Tek sayfa kaldiysa serit HIC cizilmez (Pager pages<=1'de null doner) -
// gunun erken saatinde "son gun" 30'dan az mac verebiliyor, test o yuzden
// iki durumu da kabul ediyor.
const dayPages = Math.max(1, Math.ceil(dayTotal2 / 30))
check('süzgeç sonrası 1. sayfa',
  dayPages === 1 ? !doc.querySelector('.pager')
                 : doc.querySelector('.pager button.primary')?.textContent.trim() === '1',
  `${dayTotal2} maç -> ${dayPages} sayfa`)
check('"Son gün" işaretli', sonGun.className.includes('primary'))
check('özette tarih yazılı', /Tarih: \d\d\.\d\d\.\d{4}/.test(summary()), summary().slice(-40))

await click(tumu, 4500)
check('"Tümü" filtreyi kaldırdı', totalOf(summary()) >= allTotal, `${dayTotal2} -> ${totalOf(summary())}`)

check('konsol temiz', errors.length === 0, errors[0] ? errors[0].slice(0, 200) : '')
console.log(failed ? `\n${failed} kontrol BASARISIZ` : '\nhepsi gecti')
process.exit(failed ? 1 : 0)
