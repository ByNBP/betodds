/**
 * Taktik kutusunun kurallarini gercek render uzerinden dogrular.
 *
 * Kurallar zamana ve esige bagli (son 2 dakika, tam oran cifti); canli veriyle
 * beklemek yerine /api/dashboard yaniti araya girilip elde edilmis maclarla
 * degistiriliyor. Boylece hem tetiklenen hem TETIKLENMEYEN durumlar test
 * edilebiliyor - yanlis pozitif, kacirilmis uyari kadar kotu.
 *
 * Kullanim:  SMOKE_URL=http://127.0.0.1:8000/ node scripts/smoke-tactics.mjs
 */
import * as esbuild from 'esbuild'
import { JSDOM, VirtualConsole } from 'jsdom'

const base = process.env.SMOKE_URL || 'http://127.0.0.1:8000/'

const built = await esbuild.build({
  entryPoints: ['src/main.jsx'],
  bundle: true, write: false, format: 'iife', platform: 'browser',
  jsx: 'automatic',
  loader: { '.js': 'jsx', '.jsx': 'jsx', '.css': 'empty' },
  define: { 'process.env.NODE_ENV': '"development"' },
  logLevel: 'silent',
})
const bundle = built.outputFiles[0].text

// Gercek pano yanitini iskelet olarak alip 'live' listesini biz yaziyoruz:
// diger alanlar (kapsama, trendler...) sayfanin render olmasi icin gerekli.
const real = await (await fetch(new URL('/api/dashboard', base))).json()
const champ = real.live[0]?.champ_id ?? real.by_league[0]?.champ_id

const now = Math.floor(Date.now() / 1000)
const MIN = 11          // match_minutes
const base_m = (over) => ({
  champ_id: champ, league_name: 'Test Ligi', status: 'live',
  home: 'EV', away: 'DEP', home_id: 1, away_id: 2,
  start_ts: now - Math.round((MIN - over) * 60),   // 'over' dakika kaldi
  match_minutes: MIN, status_text: '', tourney_id: null, iteration: null,
  first_seen: now, last_update: now, finished_at: null, missing: 0,
  prematch_missed: 0, source: null, has_snapshot: 0, snapshot_markets: null,
  o1: 2, ox: 6, o2: 2, p1: 2, px: 6, p2: 2,
  score_home: 3, score_away: 3, expect: null, predict: null, h2h: null,
  home_pos: null, away_pos: null, pos_current: false, pos_iteration: null,
})

const cases = [
  { id: 1, name: 'KG: 1 dk kaldi, deplasman 0 -> uyari',
    m: { ...base_m(1), event_id: 901, score_home: 4, score_away: 0 },
    expect: 'TAKTİK KG VAR OYNA', want: true },
  { id: 2, name: 'KG: 5 dk kaldi, deplasman 0 -> uyari YOK',
    m: { ...base_m(5), event_id: 902, score_home: 4, score_away: 0 },
    expect: 'TAKTİK KG VAR OYNA', want: false },
  { id: 3, name: 'KG: 1 dk kaldi ama iki taraf da golu var -> uyari YOK',
    m: { ...base_m(1), event_id: 903, score_home: 4, score_away: 2 },
    expect: 'TAKTİK KG VAR OYNA', want: false },
  { id: 4, name: 'Oran: 2.52-1.94 -> uyari',
    m: { ...base_m(8), event_id: 904, p1: 2.52, p2: 1.94 },
    expect: 'ORAN TAKTİĞİ BOL GOL!(2.52-1.94)', want: true },
  { id: 5, name: 'Oran: 2.60-1.94 -> uyari YOK',
    m: { ...base_m(8), event_id: 905, p1: 2.60, p2: 1.94 },
    expect: 'ORAN TAKTİĞİ BOL GOL!', want: false },
  { id: 6, name: 'Sira rozeti: home_pos/away_pos gosteriliyor',
    m: { ...base_m(8), event_id: 906, home_pos: 7, away_pos: 12 },
    expect: '7.', want: true },
  // Kalibrasyon islemi kartta yaziyor mu: gosterilen sayi ham market
  // beklentisi degil, kullanici bunu gorebilmeli.
  { id: 7, name: 'Kalibrasyon islemi kartta gosteriliyor',
    m: { ...base_m(8), event_id: 907,
         expect: { total: 9.5, total_raw: 10.17, home: 5.0, away: 4.5,
                   adjust: { offset: 0.5, step: 0.5 },
                   top_total: 9, top_prob: 12, line: 9.5, remaining: null } },
    expect: '(10.17 − 0.5)', want: true },
]

const payload = { ...real, live: cases.map((c) => c.m) }

const errors = []
const vc = new VirtualConsole()
vc.on('jsdomError', (e) => errors.push(`jsdomError: ${e.message}`))
vc.on('error', (...a) => errors.push(`console.error: ${a.join(' ')}`))

const dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>', {
  url: new URL(`/lig/${champ}`, base).href,
  runScripts: 'dangerously', pretendToBeVisual: true, virtualConsole: vc,
})
const { window } = dom
window.EventSource = class { constructor() { this.readyState = 0 } close() {} }
window.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} }
const nodeFetch = globalThis.fetch
window.fetch = (input, init) => {
  const url = typeof input === 'string' ? new URL(input, base).toString() : input
  if (String(url).includes('/api/dashboard')) {
    // jsdom'da Response yok; api.js yalnizca ok + json() kullaniyor.
    return Promise.resolve({ ok: true, status: 200, json: async () => payload })
  }
  return nodeFetch(url, init)
}

window.eval(bundle)
await new Promise((r) => setTimeout(r, 3500))

const cards = [...window.document.querySelectorAll('.match-left')]
let bad = 0
console.log('')
for (const c of cases) {
  // Kartlar 'live' listesindeki sirayla basiliyor.
  const el = cards[cases.indexOf(c)]
  const txt = (el?.textContent || '').replace(/\s+/g, ' ')
  const got = txt.includes(c.expect)
  const ok = got === c.want
  if (!ok) bad++
  console.log(`  ${ok ? '✓' : '✗'} ${c.name}`)
  if (!ok) console.log(`      beklenen ${c.want ? 'VAR' : 'YOK'}, bulunan: "${txt.slice(0, 120)}"`)
}

if (errors.length) {
  bad++
  console.log('\n  ✗ konsol hatasi:')
  errors.slice(0, 5).forEach((e) => console.log(`      ${e}`))
} else {
  console.log('  ✓ konsol temiz')
}

console.log(bad ? `\n${bad} kontrol BASARISIZ` : '\nhepsi gecti')
process.exit(bad ? 1 : 0)
