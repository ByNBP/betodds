import { useState } from 'react'

/**
 * Sayfa numaralari - listenin altinda, dogrudan atlamak icin.
 *
 * Ileri/geri butonlari uzun arsivde ise yaramiyordu: 51 sayfanin 40.'sina
 * gitmek 39 tiklama demekti. Numaralar dogrudan hedefe goturur.
 *
 * Ilk ve son sayfa HER ZAMAN gorunur; aradaki bosluklar "…" ile kisalir,
 * boylece serit sayfa sayisindan bagimsiz olarak ayni genislikte kalir.
 * Elips yalnizca EN AZ IKI sayfa gizliyorsa konur - tek sayfayi "…" ile
 * ortmek ne yer kazandirir ne de bir sey anlatir.
 */
const WINDOW = 2   // gecerli sayfanin iki yanindaki komsu sayisi
const JUMP_FROM = 10   // bu sayfadan sonrasinda numaralar tek basina yetmiyor

export function pageList(page, pages) {
  const keep = new Set([1, pages])
  for (let p = page - WINDOW; p <= page + WINDOW; p++) {
    if (p >= 1 && p <= pages) keep.add(p)
  }
  const out = []
  let prev = 0
  for (const p of [...keep].sort((a, b) => a - b)) {
    if (prev && p - prev > 1) out.push(p - prev === 2 ? prev + 1 : '…')
    out.push(p)
    prev = p
  }
  return out
}

export default function Pager({ page, pages, onPage }) {
  const [jump, setJump] = useState('')
  if (pages <= 1) return null

  const go = (p) => onPage(Math.min(pages, Math.max(1, p)))
  const submitJump = (e) => {
    e.preventDefault()
    const n = Number(jump)
    if (Number.isInteger(n) && n >= 1 && n <= pages) { go(n); setJump('') }
  }

  return (
    <nav className="pager" aria-label="Sayfalar">
      <button disabled={page === 1} onClick={() => go(page - 1)}>← Önceki</button>

      {pageList(page, pages).map((p, i) => (p === '…'
        ? <span key={`gap-${i}`} className="pager-gap" aria-hidden="true">…</span>
        : <button key={p} className={p === page ? 'primary' : ''}
            aria-current={p === page ? 'page' : undefined}
            aria-label={`Sayfa ${p}`} onClick={() => go(p)}>{p}</button>))}

      <button disabled={page === pages} onClick={() => go(page + 1)}>Sonraki →</button>

      {/* Numaralarin arasi elipsle kisaldigi icin uzak sayfalar seritte hic
          gorunmuyor; kutu onlara da tek adimda gitmeyi birakiyor. */}
      {pages >= JUMP_FROM && (
        <form className="pager-jump" onSubmit={submitJump}>
          <input type="number" min="1" max={pages} value={jump} placeholder={page}
            onChange={(e) => setJump(e.target.value)}
            aria-label={`Sayfaya git (1-${pages})`} title={`1 - ${pages}`} />
          <span className="muted">/ {pages}</span>
          <button type="submit" disabled={!jump}>Git</button>
        </form>
      )}
    </nav>
  )
}
