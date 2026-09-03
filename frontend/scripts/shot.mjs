/** Gercek tarayicida ekran goruntusu alir (grafik geometrisini gozle dogrulamak icin). */
import puppeteer from 'puppeteer-core'

const url = process.env.SHOT_URL || 'http://127.0.0.1:8000/'
const out = process.env.SHOT_OUT || 'shot.png'

const browser = await puppeteer.launch({
  executablePath: process.env.CHROME || '/usr/bin/chromium-browser',
  args: ['--no-sandbox', '--disable-dev-shm-usage'],
})
const page = await browser.newPage()
await page.setViewport({ width: 1280, height: 1400, deviceScaleFactor: 1 })

const errors = []
page.on('pageerror', (e) => errors.push(String(e).slice(0, 200)))
page.on('console', (m) => m.type() === 'error' && errors.push(m.text().slice(0, 200)))

// Sayfa surekli acik bir SSE baglantisi tutuyor; 'networkidle' asla gelmez.
await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 45000 })
await new Promise((r) => setTimeout(r, 4000))   // veri + grafik yerlesimi

const svgs = await page.$$eval('svg.recharts-surface',
  (els) => els.map((e) => ({ w: e.clientWidth || +e.getAttribute('width'),
                             h: e.clientHeight || +e.getAttribute('height') })))
const bars = await page.$$eval('.recharts-bar-rectangle', (e) => e.length)
const lines = await page.$$eval('.recharts-line-curve', (e) => e.length)

await page.screenshot({ path: out, fullPage: true })
await browser.close()

console.log(`  svg (recharts): ${svgs.length} -> ${JSON.stringify(svgs)}`)
console.log(`  cubuk: ${bars}   cizgi: ${lines}`)
console.log(`  konsol hatasi: ${errors.length}`)
errors.slice(0, 3).forEach((e) => console.log('   ', e))
console.log(`  kaydedildi: ${out}`)
