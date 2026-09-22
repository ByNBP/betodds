import { useEffect } from 'react'

/**
 * Sekme basligini acilan sayfanin adina cevirir.
 *
 * Tek bir sabit baslikla ("BetOdds — Canlı Oran Takibi") birden fazla sekme
 * acildiginda hangisinin hangi sayfa oldugu ayirt edilemiyordu. Sayfa adi
 * ONE gelir: sekme seridi darken once o kirpilir.
 *
 * `null` verilirse (veri henuz yuklenmediyse) baslik degistirilmez - bir
 * kare boyunca "BetOdds" yazip sonra ada donmesi goz tirmaliyordu.
 */
export const SITE = 'BetOdds'

export default function useTitle(name) {
  useEffect(() => {
    if (name) document.title = `${name} · ${SITE}`
  }, [name])
}
