import puppeteer from 'puppeteer-core'
const b = await puppeteer.launch({ executablePath: '/usr/bin/chromium-browser',
  args: ['--no-sandbox','--disable-dev-shm-usage'] })
const p = await b.newPage()
await p.setViewport({ width: 1280, height: 1000 })
await p.goto(process.env.SHOT_URL || 'http://127.0.0.1:8000/', { waitUntil: 'domcontentloaded' })
await new Promise(r => setTimeout(r, 4000))
// DIKKAT: bu fonksiyon tarayicida calisir, process.env orada yok - arguman gecir.
const panelText = process.env.SHOT_PANEL || 'Sezon trendi'
const h = await p.evaluateHandle(
  (needle) => [...document.querySelectorAll('.panel')].find(x => x.textContent.includes(needle)),
  panelText)
if (!h.asElement()) { console.error(`  panel bulunamadi: "${panelText}"`); await b.close(); process.exit(1) }
const el = h.asElement()
await el.scrollIntoView()
await new Promise(r => setTimeout(r, 1200))
await el.screenshot({ path: process.env.SHOT_OUT || '/app/shot-el.png' })
console.log('  panel goruntusu alindi')
await b.close()
