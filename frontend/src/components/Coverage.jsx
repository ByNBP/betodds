import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api.js'
import { fmtDateTime, STATUS_LABEL } from '../format.js'

/**
 * Mac oncesi arsiv kapsamasi. "missed" satirlari geri kazanilamaz: site,
 * mac bittikten sonra oranlari tamamen siliyor.
 */
export default function Coverage({ champ }) {
  const [data, setData] = useState(null)
  const [open, setOpen] = useState(false)

  useEffect(() => {
    let alive = true
    setData(null)
    api.coverage(champ ?? undefined).then((d) => alive && setData(d)).catch(() => {})
    return () => { alive = false }
  }, [champ])
  if (!data) return null

  const s = data.summary
  const pending = data.gaps.filter((g) => g.kind === 'pending')
  const missed = data.gaps.filter((g) => g.kind === 'missed')

  return (
    <div className="panel">
      <div className="chart-head">
        <h2>Maç öncesi arşiv kapsaması</h2>
        {data.gaps.length > 0 && (
          <button onClick={() => setOpen((o) => !o)}>
            {open ? 'gizle' : `${data.gaps.length} açık`}
          </button>
        )}
      </div>

      <div className="kv" style={{ marginTop: 4 }}>
        <div><div className="k">Listelenen maç</div><div className="v">{s.listed}</div></div>
        <div><div className="k">Arşivlenen</div>
          <div className="v">{s.archived} <span className="muted" style={{ fontSize: 13 }}>%{s.pct}</span></div></div>
        <div><div className="k">Bekleyen</div>
          <div className="v" style={{ color: s.pending ? 'var(--series-2)' : undefined }}>{s.pending}</div></div>
        <div><div className="k">Kaçırılan</div>
          <div className="v" style={{ color: s.missed ? 'var(--down)' : undefined }}>{s.missed}</div></div>
        <div><div className="k">Sıradaki maçlar</div>
          <div className="v">{s.upcoming_archived}/{s.upcoming_listed}</div></div>
        <div><div className="k">Referans set</div>
          <div className="v">{s.reference_of_started}/{s.started}</div></div>
      </div>

      {s.upcoming_listed > 0 && s.upcoming_archived === s.upcoming_listed && (
        <div className="notice" style={{ marginTop: 14, marginBottom: 0 }}>
          Listelenen ve henüz oynanmamış tüm maçların tam market seti arşivlendi.
        </div>
      )}
      <div className="notice" style={{ marginTop: 10, marginBottom: 0 }}>
        <strong>Referans set</strong>, maç başlamadan hemen önce (son 3 dakika içinde,
        her poll'da tazelenerek) alınan settir. Geçerli oranlar bunlardır; maç
        içindeki değişim referans değildir. Toplayıcı bu özellikten önce kaydedilen
        maçlarda yalnızca açılış seti bulunur.
      </div>
      {s.missed > 0 && (
        <div className="notice" style={{ marginTop: 14, marginBottom: 0,
          borderLeftColor: 'var(--down)' }}>
          {s.missed} maçın maç öncesi oranı yok. Bunlar geri alınamaz — site,
          maç bittikten sonra oranları tamamen siliyor.
        </div>
      )}

      {open && (
        <div className="scroll-x" style={{ marginTop: 14 }}>
          <table>
            <thead><tr><th>Maç</th><th>Başlangıç</th><th>Durum</th>
              <th className="num">Yakalanan</th><th>Not</th></tr></thead>
            <tbody>
              {[...pending, ...missed].map((g) => (
                <tr key={g.event_id}>
                  <td><Link to={`/mac/${g.event_id}`}>{g.home} – {g.away}</Link></td>
                  <td className="muted">{fmtDateTime(g.start_ts)}</td>
                  <td>{STATUS_LABEL[g.status] || g.status}</td>
                  <td className="num">{g.snapshot_markets ?? '—'}</td>
                  <td className="muted">
                    {g.kind === 'pending' ? 'başlamadan yakalanacak' : 'geri alınamaz'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
