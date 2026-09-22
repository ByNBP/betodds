import FinishedTable from './FinishedTable.jsx'

/**
 * Panonun tepesindeki son biten maclar ozeti.
 *
 * Sonuclar sayfasiyla ayni tablo, ayni isaretleme: tutan her tahmin
 * yesil-kalin + tik, tutmayan kirmizi + carpi.
 */
export default function RecentFinished({ matches }) {
  if (!matches?.length) return null
  return (
    <div className="panel scroll-x recent-finished">
      <h3>Son biten {matches.length} maç</h3>
      <FinishedTable matches={matches} mark favorite />
    </div>
  )
}
