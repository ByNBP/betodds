/**
 * Cok sayfali duman testi: her rotayi ayri bir jsdom penceresinde acar ve
 * secili ligin gercekten uygulandigini dogrular.
 *
 * smoke.mjs yalnizca "/" rotasini yukluyor; her ligin kendi /lig/<id>
 * sayfasi oldugundan ve Arsiv/Istatistik son secilen ligi izledigi icin
 * hepsinin ayri ayri render edildigini gormek gerekiyor.
 *
 * Kullanim:  SMOKE_URL=http://127.0.0.1:8000/ node scripts/smoke-routes.mjs
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

// Secili ligi dogrulayabilmek icin lig listesini sunucudan alalim.
const leagues = await (await fetch(new URL('/api/leagues', base))).json()

async function render(path, champ) {
  const errors = []
  const vc = new VirtualConsole()
  vc.on('jsdomError', (e) => errors.push(`jsdomError: ${e.message}`))
  vc.on('error', (...a) => errors.push(`console.error: ${a.join(' ')}`))

  const dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>', {
    url: new URL(path, base).toString(),
    runScripts: 'dangerously', pretendToBeVisual: true, virtualConsole: vc,
  })
  const { window } = dom
  window.EventSource = class { constructor() { this.readyState = 0 } close() {} }
  window.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} }
  const nodeFetch = globalThis.fetch
  window.fetch = (input, init) => nodeFetch(
    typeof input === 'string' && input.startsWith('/')
      ? new URL(input, base).toString() : input, init)
  if (champ != null) window.localStorage.setItem('betodds.champ', String(champ))

  window.eval(bundle)
  await new Promise((r) => setTimeout(r, 3500))
  const text = (window.document.body.textContent || '').replace(/\s+/g, ' ')
  const rows = window.document.querySelectorAll('.card, table tbody tr').length
  const now = window.document.querySelector('.league-now')
  const selected = now ? now.textContent.trim() : null
  const active = window.document.querySelector('nav.tabs a.active')
  const activeTab = active ? active.textContent.trim() : null
  window.close()
  return { text, rows, errors, selected, activeTab }
}

let failed = 0
const check = (name, ok, extra = '') => {
  console.log(`  ${ok ? '✓' : '✗'} ${name}${extra ? '  ' + extra : ''}`)
  if (!ok) failed++
}

for (const l of leagues) {
  console.log(`\n=== ${l.name} (champ ${l.champ_id}) ===`)
  for (const [label, path] of [['Lig sayfası', `/lig/${l.champ_id}`],
                               ['Arşiv', '/arsiv'],
                               ['Sonuçlar', '/sonuclar']]) {
    const r = await render(path, l.champ_id)
    check(`${label} render`, r.text.includes('BetOdds') && !r.text.includes('Sayfa bulunamadı'),
          `satır:${r.rows}`)
    check(`${label} doğru lig gösteriliyor`, r.selected === l.name,
          `başlıkta:${r.selected}`)
    check(`${label} konsol temiz`, r.errors.length === 0,
          r.errors[0] ? r.errors[0].slice(0, 120) : '')
    if (path.startsWith('/lig/')) {
      check(`${label} sekmesi aktif`, r.activeTab === (l.short_name || l.name),
            `aktif:${r.activeTab}`)
    }
  }
}

console.log(failed ? `\n${failed} kontrol BASARISIZ` : '\nhepsi gecti')
process.exit(failed ? 1 : 0)
