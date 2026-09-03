/**
 * Frontend duman testi: uygulamayi jsdom icinde gercekten calistirir.
 * Build'in gecmesi render'in calistigini kanitlamaz; bu test React'in mount
 * oldugunu, backend'den veri cektigini ve konsola hata dusmedigini dogrular.
 *
 * jsdom `<script type="module">` calistirmadigi icin kaynak, esbuild ile
 * klasik (IIFE) bir pakete derlenip sayfaya enjekte edilir.
 *
 * Kullanim:  SMOKE_URL=http://127.0.0.1:8000/ node scripts/smoke.mjs
 */
import * as esbuild from 'esbuild'
import { JSDOM, VirtualConsole } from 'jsdom'

const base = process.env.SMOKE_URL || 'http://127.0.0.1:8000/'

const built = await esbuild.build({
  entryPoints: ['src/main.jsx'],
  bundle: true,
  write: false,
  format: 'iife',
  platform: 'browser',
  // Vite'in plugin-react'i otomatik JSX runtime kullaniyor; esbuild'in
  // varsayilani klasik donusum oldugu icin burada acikca eslestiriyoruz.
  jsx: 'automatic',
  loader: { '.js': 'jsx', '.jsx': 'jsx', '.css': 'empty' },
  define: { 'process.env.NODE_ENV': '"development"' },
  logLevel: 'silent',
})
const bundle = built.outputFiles[0].text

const errors = []
const vc = new VirtualConsole()
vc.on('jsdomError', (e) => errors.push(`jsdomError: ${e.message}`))
vc.on('error', (...a) => errors.push(`console.error: ${a.join(' ')}`))

const dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>', {
  url: base,
  runScripts: 'dangerously',
  pretendToBeVisual: true,
  virtualConsole: vc,
})
const { window } = dom

// jsdom'da bulunmayan tarayici API'leri
window.EventSource = class {
  constructor() { this.readyState = 0 }
  close() {}
}
window.ResizeObserver = class {
  observe() {} unobserve() {} disconnect() {}
}
const nodeFetch = globalThis.fetch
window.fetch = (input, init) => {
  const url = typeof input === 'string' && input.startsWith('/')
    ? new URL(input, base).toString()
    : input
  return nodeFetch(url, init)
}

window.eval(bundle)

const wait = (ms) => new Promise((r) => setTimeout(r, ms))
await wait(3500)

const { document } = window
const text = (document.body.textContent || '').replace(/\s+/g, ' ')
const cards = document.querySelectorAll('.card, table tbody tr').length

const checks = [
  ['React mount oldu', document.querySelector('#root')?.children.length > 0],
  ['Marka görünüyor', text.includes('BetOdds')],
  // Gezinme cubugu artik lig basina sekme + Arsiv/Istatistik. Metinde
  // 'Canlı' aramak yanlis pozitif veriyordu ('Canlı maç' KPI kutusu).
  ['Navigasyon var', document.querySelectorAll('nav.tabs a').length >= 3],
  ['Lig sayfasina yonlendirildi', /\/lig\/\d+/.test(window.location.pathname)],
  ['Backend sağlığı okundu', /\d+ maç/.test(text)],
  ['Sayfa içeriği geldi', !text.includes('Yükleniyor…')],
  ['Konsol hatası yok', errors.length === 0],
]

let failed = 0
for (const [name, ok] of checks) {
  console.log(`  ${ok ? '✓' : '✗'} ${name}`)
  if (!ok) failed++
}
if (errors.length) {
  console.log('\n  Hatalar:')
  errors.slice(0, 5).forEach((e) => console.log('   ', e.slice(0, 220)))
}
console.log(`\n  kart/satır: ${cards}`)
console.log(`  görünen metin: ${text.slice(0, 220)}…`)
window.close()
process.exit(failed ? 1 : 0)
