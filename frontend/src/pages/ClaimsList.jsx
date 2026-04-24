import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { listClaims } from '../api.js'

const decisionColor = { APPROVED: '#16a34a', PARTIAL: '#d97706', REJECTED: '#dc2626', MANUAL_REVIEW: '#7c3aed' }
const statusColor = { COMPLETED: '#16a34a', PROCESSING: '#2563eb', ERROR: '#dc2626' }

function Tag({ label, color }) {
  return (
    <span style={{
      display: 'inline-block', padding: '2px 8px', borderRadius: 4, fontSize: 11,
      fontWeight: 700, background: color + '22', color,
    }}>{label}</span>
  )
}

export default function ClaimsList() {
  const [claims, setClaims] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    listClaims()
      .then(setClaims)
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <p>Loading…</p>

  return (
    <div>
      <h2 style={{ marginBottom: '1.5rem', fontWeight: 700 }}>All Claims</h2>
      {claims.length === 0 && <p style={{ color: '#888' }}>No claims submitted yet.</p>}
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
        <thead>
          <tr style={{ background: '#1a1a2e', color: '#fff' }}>
            {['Claim ID', 'Member', 'Category', 'Treatment Date', 'Claimed', 'Status', 'Decision', 'Approved', 'Confidence', ''].map(h => (
              <th key={h} style={{ padding: '10px 12px', textAlign: 'left', fontWeight: 600 }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {claims.map((c, i) => (
            <tr key={c.claim_id} style={{ background: i % 2 === 0 ? '#fff' : '#f9fafb' }}>
              <td style={{ padding: '10px 12px', fontWeight: 600, color: '#7c83fd' }}>
                <Link to={`/claims/${c.claim_id}`} style={{ color: '#7c83fd', textDecoration: 'none' }}>{c.claim_id}</Link>
              </td>
              <td style={{ padding: '10px 12px' }}>{c.member_id}</td>
              <td style={{ padding: '10px 12px' }}>{c.claim_category}</td>
              <td style={{ padding: '10px 12px' }}>{c.treatment_date?.slice(0, 10)}</td>
              <td style={{ padding: '10px 12px' }}>₹{Number(c.claimed_amount).toLocaleString('en-IN')}</td>
              <td style={{ padding: '10px 12px' }}>
                <Tag label={c.status} color={statusColor[c.status] || '#888'} />
              </td>
              <td style={{ padding: '10px 12px' }}>
                {c.decision && <Tag label={c.decision} color={decisionColor[c.decision] || '#888'} />}
              </td>
              <td style={{ padding: '10px 12px' }}>
                {c.approved_amount != null ? `₹${Number(c.approved_amount).toLocaleString('en-IN')}` : '—'}
              </td>
              <td style={{ padding: '10px 12px' }}>
                {c.confidence_score != null ? `${(c.confidence_score * 100).toFixed(0)}%` : '—'}
              </td>
              <td style={{ padding: '10px 12px' }}>
                <Link to={`/claims/${c.claim_id}`} style={{ color: '#7c83fd', fontSize: 12 }}>View →</Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
