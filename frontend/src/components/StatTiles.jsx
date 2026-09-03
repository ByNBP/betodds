/** KPI seridi. Bunlar tekil sayilar - grafik degil, stat tile. */
export default function StatTiles({ data }) {
  const c = data?.counts || {}
  const cov = data?.coverage
  const tiles = [
    { k: 'Canlı maç', v: c.live ?? 0,
      sub: `${c.scheduled ?? 0} maç sırada` },
    { k: 'Maç öncesi arşiv', v: cov ? `%${cov.pct ?? 0}` : (c.snapshots ?? 0),
      sub: cov
        ? `${cov.archived}/${cov.listed} maç · ${cov.missed} kaçırıldı`
        : 'tam market seti' },
    { k: 'Oran kaydı', v: (c.ticks ?? 0).toLocaleString('tr-TR'),
      sub: 'zaman serisi noktası' },
    { k: 'Maç başı gol', v: data?.avg_goals ?? '—',
      sub: data?.avg_goals_sample ? `${data.avg_goals_sample} biten maçtan` : 'henüz veri yok' },
  ]
  return (
    <div className="tiles">
      {tiles.map((t) => (
        <div className="tile" key={t.k}>
          <div className="k">{t.k}</div>
          <div className="v">{t.v}</div>
          <div className="sub">{t.sub}</div>
        </div>
      ))}
    </div>
  )
}
