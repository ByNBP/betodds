import { fmtOdd } from '../format.js'

/* Isaretler font glifi degil satir ici SVG: ✓/✗ karakterleri her fontta
   bulunmuyor ve eksik oldugunda anlami yalnizca renk tasir. */
function Mark({ kind }) {
  const common = { width: 11, height: 11, viewBox: '0 0 12 12', fill: 'none',
    strokeWidth: 2, strokeLinecap: 'round', strokeLinejoin: 'round',
    style: { flex: 'none', marginRight: 5 } }
  if (kind === 'won') {
    return <svg {...common} stroke="var(--good)" aria-label="tuttu">
      <path d="M2 6.5 L4.8 9.3 L10 3.2" /></svg>
  }
  if (kind === 'void') {
    return <svg {...common} stroke="var(--warning)" aria-label="iade">
      <path d="M2 4.5 H10 M2 7.5 H10" /></svg>
  }
  if (kind === 'lost') {
    return <svg {...common} stroke="currentColor" aria-label="tutmadı">
      <path d="M3 3 L9 9 M9 3 L3 9" /></svg>
  }
  return null
}

export default function MarketGroups({ groups, settled }) {
  if (!groups?.length) return <div className="empty">Market bulunamadı.</div>
  return (
    <>
      {settled && (
        <div className="legend-row">
          <span><Mark kind="won" />tuttu</span>
          <span><Mark kind="lost" />tutmadı</span>
          <span><Mark kind="void" />iade (çizgiye tam eşit)</span>
          <span>işaretsiz: final skordan belirlenemiyor</span>
        </div>
      )}
      {groups.map((g) => (
        <div className={`market ${g.settleable === false ? 'unsettleable' : ''}`} key={g.g}>
          <h3>
            {g.label} <span className="muted">({g.outcomes.length})</span>
            {settled && g.settleable === false && (
              <span className="note">— bu market final skordan belirlenemiyor</span>
            )}
          </h3>
          <div className="market-outcomes">
            {g.outcomes.map((o, i) => (
              <div key={`${o.t}-${o.p}-${i}`}
                className={`outcome ${o.blocked ? 'blocked' : ''} ${o.result || ''}`}>
                <span className="lbl"><Mark kind={o.result} />{o.label}</span>
                <span className="val">{fmtOdd(o.coef)}</span>
              </div>
            ))}
          </div>
        </div>
      ))}
    </>
  )
}
