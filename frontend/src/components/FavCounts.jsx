/**
 * Filtredeki biten maclarda favori / surpriz kazanan sayisi. Kural sonuc
 * tablolarindaki "Favori / Surpriz" sutunuyla ayni (backend _fav_counts):
 * mac oncesi orani dusuk taraf favori. Yuzde yalnizca kazanani olan maclar
 * uzerinden; beraberlik ayri yaziliyor.
 */
export default function FavCounts({ fav }) {
  if (!fav || fav.favorite + fav.surprise + fav.draw === 0) return null
  return (
    <div className="fav-counts">
      <span className="badge fav">Favori</span>
      <strong>{fav.favorite}</strong>
      {fav.favorite_pct != null && <span className="muted">%{fav.favorite_pct}</span>}
      <span className="badge surprise">Sürpriz</span>
      <strong>{fav.surprise}</strong>
      {fav.surprise_pct != null && <span className="muted">%{fav.surprise_pct}</span>}
      <span className="muted">· beraberlik {fav.draw}</span>
      {fav.unknown > 0 && (
        <span className="muted" title="Maç öncesi oranı olmayan ya da oranları eşit maçlar">
          · favorisi belirsiz {fav.unknown}
        </span>
      )}
    </div>
  )
}
