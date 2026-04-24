import React, { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { getClaim } from '../api.js'

const decisionColor = { APPROVED: '#16a34a', PARTIAL: '#d97706', REJECTED: '#dc2626', MANUAL_REVIEW: '#7c3aed' }
const stepColor = { SUCCESS: '#16a34a', FAILED: '#dc2626', PARTIAL: '#d97706', ISSUES_FOUND: '#d97706', SKIPPED: '#888' }

function Tag({ label, color }) {
  return <span style={{ display: 'inline-block', padding: '3px 10px', borderRadius: 4, fontSize: 12, fontWeight: 700, background: color + '22', color }}>{label}</span>
}

function Section({ title, children }) {
  return (
    <div style={{ background: '#fff', borderRadius: 8, padding: '1.5rem', boxShadow: '0 1px 4px rgba(0,0,0,.08)', marginBottom: '1.5rem' }}>
      <h3 style={{ fontWeight: 700, marginBottom: '1rem', fontSize: 15 }}>{title}</h3>
      {children}
    </div>
  )
}

function KV({ k, v }) {
  return (
    <div style={{ display: 'flex', gap: 8, marginBottom: 6, fontSize: 13 }}>
      <span style={{ fontWeight: 600, color: '#555', minWidth: 160 }}>{k}</span>
      <span>{v ?? '—'}</span>
    </div>
  )
}

export default function ClaimDetail() {
  const { id } = useParams()
  const [claim, setClaim] = useState(null)
  const [loading, setLoading] = useState(true)
  const [expandedStep, setExpandedStep] = useState(null)

  useEffect(() => {
    getClaim(id).then(setClaim).finally(() => setLoading(false))
  }, [id])

  if (loading) return <p>Loading…</p>
  if (!claim) return <p>Claim not found.</p>

  const color = decisionColor[claim.decision] || '#888'

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '1.5rem' }}>
        <Link to="/claims" style={{ color: '#7c83fd', fontSize: 13 }}>← All Claims</Link>
        <h2 style={{ fontWeight: 700 }}>{claim.claim_id}</h2>
        {claim.decision && <Tag label={claim.decision} color={color} />}
      </div>

      <Section title="Claim Summary">
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 2rem' }}>
          <div>
            <KV k="Member ID" v={claim.member_id} />
            <KV k="Policy ID" v={claim.policy_id} />
            <KV k="Category" v={claim.claim_category} />
            <KV k="Treatment Date" v={claim.treatment_date?.slice(0, 10)} />
          </div>
          <div>
            <KV k="Claimed Amount" v={`₹${Number(claim.claimed_amount).toLocaleString('en-IN')}`} />
            <KV k="Approved Amount" v={claim.approved_amount != null ? `₹${Number(claim.approved_amount).toLocaleString('en-IN')}` : '—'} />
            <KV k="Confidence Score" v={claim.confidence_score != null ? `${(claim.confidence_score * 100).toFixed(1)}%` : '—'} />
            <KV k="Hospital" v={claim.hospital_name} />
          </div>
        </div>
        {claim.decision_notes && (
          <div style={{ marginTop: '1rem', padding: '.75rem', background: '#f5f7fa', borderRadius: 6, fontSize: 13, color: '#555' }}>
            <strong>Decision Notes:</strong> {claim.decision_notes}
          </div>
        )}
        {claim.stop_message && (
          <div style={{ marginTop: '.5rem', padding: '.75rem', background: '#fef3c7', border: '1px solid #fcd34d', borderRadius: 6, fontSize: 13 }}>
            <strong>Early Stop:</strong> {claim.stop_message}
          </div>
        )}
        {claim.rejection_reasons?.length > 0 && (
          <div style={{ marginTop: '.5rem' }}>
            <strong style={{ fontSize: 13 }}>Rejection Reasons: </strong>
            {claim.rejection_reasons.map(r => <Tag key={r} label={r} color="#dc2626" />)}
          </div>
        )}
        {claim.component_failures?.length > 0 && (
          <div style={{ marginTop: '.5rem', color: '#d97706', fontSize: 13 }}>
            ⚠ Component failures: {claim.component_failures.join(', ')}
          </div>
        )}
      </Section>

      {claim.line_item_decisions?.length > 0 && (
        <Section title="Line Item Decisions">
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ background: '#f5f7fa' }}>
                {['Description', 'Amount', 'Status', 'Reason'].map(h => (
                  <th key={h} style={{ padding: '8px 10px', border: '1px solid #e5e7eb', textAlign: 'left', fontWeight: 600 }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {claim.line_item_decisions.map((li, i) => (
                <tr key={i}>
                  <td style={{ padding: '8px 10px', border: '1px solid #e5e7eb' }}>{li.description}</td>
                  <td style={{ padding: '8px 10px', border: '1px solid #e5e7eb' }}>₹{Number(li.amount).toLocaleString('en-IN')}</td>
                  <td style={{ padding: '8px 10px', border: '1px solid #e5e7eb' }}>
                    <Tag label={li.approved ? 'APPROVED' : 'REJECTED'} color={li.approved ? '#16a34a' : '#dc2626'} />
                  </td>
                  <td style={{ padding: '8px 10px', border: '1px solid #e5e7eb', color: '#666' }}>{li.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Section>
      )}

      {claim.documents?.length > 0 && (
        <Section title="Submitted Documents">
          {claim.documents.map((doc, i) => (
            <div key={i} style={{ display: 'flex', gap: '1rem', padding: '8px 0', borderBottom: '1px solid #f0f0f0', fontSize: 13 }}>
              <span style={{ fontWeight: 600, color: '#7c83fd' }}>{doc.file_id}</span>
              <span>{doc.file_name || '—'}</span>
              <Tag label={doc.actual_type || 'UNKNOWN'} color="#7c83fd" />
              {doc.quality && doc.quality !== 'GOOD' && <Tag label={doc.quality} color="#d97706" />}
            </div>
          ))}
        </Section>
      )}

      <Section title="Pipeline Trace">
        <p style={{ fontSize: 12, color: '#888', marginBottom: '1rem' }}>
          Click a step to expand details. This trace shows exactly what the system checked and why.
        </p>
        {claim.trace?.map((step, i) => {
          const sc = stepColor[step.status] || '#888'
          const expanded = expandedStep === i
          return (
            <div key={i} style={{ marginBottom: '0.5rem' }}>
              <div
                onClick={() => setExpandedStep(expanded ? null : i)}
                style={{
                  padding: '.75rem 1rem', borderRadius: 6, cursor: 'pointer',
                  background: sc + '11', borderLeft: `3px solid ${sc}`,
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                }}
              >
                <div>
                  <span style={{ fontWeight: 700, fontSize: 13 }}>{step.step_name || step.step}</span>
                  <Tag label={step.status} color={sc} />
                  <p style={{ fontSize: 12, color: '#555', marginTop: 4 }}>{step.summary}</p>
                  {step.error && <p style={{ fontSize: 12, color: '#dc2626', marginTop: 2 }}>Error: {step.error}</p>}
                </div>
                <span style={{ color: '#888', fontSize: 12 }}>
                  {step.duration_ms != null ? `${step.duration_ms}ms` : ''} {expanded ? '▲' : '▼'}
                </span>
              </div>
              {expanded && step.details && Object.keys(step.details).length > 0 && (
                <div style={{ padding: '1rem', background: '#f5f7fa', borderRadius: '0 0 6px 6px', fontSize: 12 }}>
                  <pre style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', margin: 0 }}>
                    {JSON.stringify(step.details, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          )
        })}
      </Section>
    </div>
  )
}
