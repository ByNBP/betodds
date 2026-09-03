/**
 * Lig anahtari - segmentli buton grubu.
 *
 * Canli sayfalar gezinme cubugunda ayri sekmeler; Arsiv gibi TEK bir sayfada
 * iki ligi de gezmek istedigimiz yerlerde ise sayfayi terk etmeden lig
 * degistirmek gerekiyor. Secim uygulama genelinde ortak (App'teki `champ`),
 * boylece basliktaki lig adi ve Istatistik sayfasi da ayni ligi izler.
 */
export default function LeagueSwitch({ leagues, champ, onChange }) {
  if (!leagues || leagues.length < 2) return null
  return (
    <div className="league-switch" role="group" aria-label="Lig seçimi">
      {leagues.map((l) => (
        <button key={l.champ_id} type="button" title={l.name}
          className={l.champ_id === champ ? 'active' : ''}
          aria-pressed={l.champ_id === champ}
          onClick={() => onChange(l.champ_id)}>
          {l.short_name || l.name || l.champ_id}
        </button>
      ))}
    </div>
  )
}
