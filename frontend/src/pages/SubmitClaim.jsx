import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { submitClaim, submitClaimFiles } from '../api.js'
import TEST_CASES from '../testCases.js'

const CATEGORIES = ['CONSULTATION', 'DIAGNOSTIC', 'PHARMACY', 'DENTAL', 'VISION', 'ALTERNATIVE_MEDICINE']

const s = {
  card: { background: '#fff', borderRadius: 8, padding: '1.5rem', boxShadow: '0 1px 4px rgba(0,0,0,.08)', marginBottom: '1.5rem' },
  label: { display: 'block', marginBottom: 4, fontWeight: 600, fontSize: 13, color: '#555' },
  input: { width: '100%', padding: '8px 10px', border: '1px solid #ddd', borderRadius: 6, fontSize: 14, outline: 'none' },
  select: { width: '100%', padding: '8px 10px', border: '1px solid #ddd', borderRadius: 6, fontSize: 14, background: '#fff' },
  row: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1rem' },
  btn: { background: '#7c83fd', color: '#fff', border: 'none', borderRadius: 6, padding: '10px 24px', fontWeight: 600, cursor: 'pointer', fontSize: 14 },
  tag: (color) => ({ display: 'inline-block', padding: '2px 8px', borderRadius: 4, fontSize: 12, fontWeight: 600, background: color + '22', color }),
}

function Field({ label, children }) {
  return (
    <label style={{ display: 'block', marginBottom: '1rem' }}>
      <span style={s.label}>{label}</span>
      {children}
    </label>
  )
}

const decisionColor = { APPROVED: '#16a34a', PARTIAL: '#d97706', REJECTED: '#dc2626', MANUAL_REVIEW: '#7c3aed' }

// ── Shared claim fields used by both modes ────────────────────────────────────
function ClaimFields({ form, set }) {
  return (
    <>
      <div style={s.row}>
        <Field label="Member ID"><input style={s.input} value={form.member_id} onChange={e => set('member_id', e.target.value)} required /></Field>
        <Field label="Policy ID"><input style={s.input} value={form.policy_id} onChange={e => set('policy_id', e.target.value)} required /></Field>
      </div>
      <div style={s.row}>
        <Field label="Claim Category">
          <select style={s.select} value={form.claim_category} onChange={e => set('claim_category', e.target.value)}>
            {CATEGORIES.map(c => <option key={c}>{c}</option>)}
          </select>
        </Field>
        <Field label="Treatment Date"><input type="date" style={s.input} value={form.treatment_date} onChange={e => set('treatment_date', e.target.value)} required /></Field>
      </div>
      <div style={s.row}>
        <Field label="Claimed Amount (INR)"><input type="number" style={s.input} value={form.claimed_amount} onChange={e => set('claimed_amount', e.target.value)} required /></Field>
        <Field label="Hospital Name (optional)"><input style={s.input} value={form.hospital_name} onChange={e => set('hospital_name', e.target.value)} placeholder="e.g. Apollo Hospitals" /></Field>
      </div>
      <Field label="YTD Claims Amount (INR)"><input type="number" style={s.input} value={form.ytd_claims_amount} onChange={e => set('ytd_claims_amount', e.target.value)} /></Field>
    </>
  )
}

// ── Result display ────────────────────────────────────────────────────────────
function ResultPanel({ result, nav }) {
  const color = decisionColor[result.decision] || '#888'
  return (
    <div style={{ ...s.card, marginTop: '1.5rem', border: `2px solid ${color}` }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
        <h3 style={{ fontWeight: 700 }}>{result.claim_id}</h3>
        {result.decision && <span style={s.tag(color)}>{result.decision}</span>}
      </div>

      {result.stop_message && (
        <div style={{ background: '#fef3c7', border: '1px solid #fcd34d', borderRadius: 6, padding: '.75rem', marginBottom: '1rem' }}>
          <strong>Early Stop:</strong> {result.stop_message}
        </div>
      )}

      {result.approved_amount != null && <p style={{ marginBottom: '.5rem' }}><strong>Approved Amount:</strong> INR {result.approved_amount.toLocaleString('en-IN')}</p>}
      {result.confidence_score != null && <p style={{ marginBottom: '.5rem' }}><strong>Confidence:</strong> {(result.confidence_score * 100).toFixed(1)}%</p>}
      {result.decision_notes && <p style={{ marginBottom: '.5rem', color: '#555', fontSize: 13 }}><strong>Notes:</strong> {result.decision_notes}</p>}
      {result.rejection_reasons?.length > 0 && <p style={{ marginBottom: '.5rem' }}><strong>Rejection Reasons:</strong> {result.rejection_reasons.join(', ')}</p>}
      {result.component_failures?.length > 0 && <p style={{ color: '#d97706', fontSize: 13 }}>Warning: component failures — {result.component_failures.join(', ')}</p>}

      {result.line_item_decisions?.length > 0 && (
        <div style={{ marginTop: '1rem' }}>
          <p style={{ fontWeight: 600, marginBottom: '.5rem' }}>Line Items</p>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead><tr style={{ background: '#f5f7fa' }}>
              {['Description', 'Amount', 'Status', 'Reason'].map(h => <th key={h} style={{ textAlign: 'left', padding: '6px 8px', border: '1px solid #e5e7eb' }}>{h}</th>)}
            </tr></thead>
            <tbody>
              {result.line_item_decisions.map((li, i) => (
                <tr key={i}>
                  <td style={{ padding: '6px 8px', border: '1px solid #e5e7eb' }}>{li.description}</td>
                  <td style={{ textAlign: 'right', padding: '6px 8px', border: '1px solid #e5e7eb' }}>INR {li.amount.toLocaleString('en-IN')}</td>
                  <td style={{ padding: '6px 8px', border: '1px solid #e5e7eb', textAlign: 'center' }}>
                    <span style={s.tag(li.approved ? '#16a34a' : '#dc2626')}>{li.approved ? 'APPROVED' : 'REJECTED'}</span>
                  </td>
                  <td style={{ padding: '6px 8px', border: '1px solid #e5e7eb', color: '#666' }}>{li.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div style={{ marginTop: '1.5rem' }}>
        <p style={{ fontWeight: 600, marginBottom: '.75rem' }}>Pipeline Trace</p>
        {result.trace.map((step, i) => (
          <div key={i} style={{
            padding: '.6rem .75rem', marginBottom: '.4rem', borderRadius: 6,
            background: step.status === 'SUCCESS' ? '#f0fdf4' : step.status === 'FAILED' ? '#fef2f2' : '#fefce8',
            borderLeft: `3px solid ${step.status === 'SUCCESS' ? '#16a34a' : step.status === 'FAILED' ? '#dc2626' : '#d97706'}`,
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <strong style={{ fontSize: 13 }}>{step.step}</strong>
              <span style={{ fontSize: 12, color: '#888' }}>{step.duration_ms}ms</span>
            </div>
            <p style={{ fontSize: 13, color: '#555', marginTop: 3 }}>{step.summary}</p>
            {step.error && <p style={{ fontSize: 12, color: '#dc2626' }}>{step.error}</p>}
          </div>
        ))}
      </div>

      <button style={{ ...s.btn, marginTop: '1rem', background: '#1a1a2e' }} onClick={() => nav(`/claims/${result.claim_id}`)}>
        View Full Detail →
      </button>
    </div>
  )
}

// ── JSON / test-case mode ─────────────────────────────────────────────────────
function JsonMode() {
  const nav = useNavigate()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [result, setResult] = useState(null)
  const [selectedTC, setSelectedTC] = useState('')
  const [form, setForm] = useState({
    member_id: 'EMP001', policy_id: 'PLUM_GHI_2024',
    claim_category: 'CONSULTATION', treatment_date: '2024-11-01',
    claimed_amount: '1500', hospital_name: '', ytd_claims_amount: '0',
    simulate_component_failure: false,
    documents_json: '[]', claims_history_json: '[]',
  })

  function loadTC(tc_id) {
    const tc = TEST_CASES.find(t => t.case_id === tc_id)
    if (!tc) return
    const i = tc.input
    setSelectedTC(tc_id)
    setForm({
      member_id: i.member_id, policy_id: i.policy_id,
      claim_category: i.claim_category, treatment_date: i.treatment_date,
      claimed_amount: String(i.claimed_amount), hospital_name: i.hospital_name || '',
      ytd_claims_amount: String(i.ytd_claims_amount || 0),
      simulate_component_failure: i.simulate_component_failure || false,
      documents_json: JSON.stringify(i.documents, null, 2),
      claims_history_json: JSON.stringify(i.claims_history || [], null, 2),
    })
    setResult(null); setError(null)
  }

  function set(k, v) { setForm(f => ({ ...f, [k]: v })) }

  async function handleSubmit(e) {
    e.preventDefault()
    setLoading(true); setError(null); setResult(null)
    try {
      const res = await submitClaim({
        member_id: form.member_id, policy_id: form.policy_id,
        claim_category: form.claim_category, treatment_date: form.treatment_date,
        claimed_amount: parseFloat(form.claimed_amount),
        hospital_name: form.hospital_name || null,
        ytd_claims_amount: parseFloat(form.ytd_claims_amount) || 0,
        simulate_component_failure: form.simulate_component_failure,
        documents: JSON.parse(form.documents_json),
        claims_history: JSON.parse(form.claims_history_json),
      })
      setResult(res)
    } catch (err) { setError(err.message) }
    finally { setLoading(false) }
  }

  return (
    <>
      <div style={s.card}>
        <p style={{ fontWeight: 600, marginBottom: '.5rem' }}>Load a test case</p>
        <select style={s.select} value={selectedTC} onChange={e => loadTC(e.target.value)}>
          <option value="">— Select test case —</option>
          {TEST_CASES.map(tc => <option key={tc.case_id} value={tc.case_id}>{tc.case_id}: {tc.case_name}</option>)}
        </select>
      </div>

      <form onSubmit={handleSubmit}>
        <div style={s.card}>
          <p style={{ fontWeight: 600, marginBottom: '1rem' }}>Member &amp; Claim Details</p>
          <ClaimFields form={form} set={set} />
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: '.5rem' }}>
            <input type="checkbox" checked={form.simulate_component_failure} onChange={e => set('simulate_component_failure', e.target.checked)} />
            <span style={{ fontSize: 13, fontWeight: 600, color: '#555' }}>Simulate component failure (TC011)</span>
          </label>
        </div>

        <div style={s.card}>
          <Field label="Documents (JSON array)">
            <textarea style={{ ...s.input, height: 180, fontFamily: 'monospace', fontSize: 12 }}
              value={form.documents_json} onChange={e => set('documents_json', e.target.value)} required />
          </Field>
          <Field label="Claims History (JSON array — for fraud check)">
            <textarea style={{ ...s.input, height: 80, fontFamily: 'monospace', fontSize: 12 }}
              value={form.claims_history_json} onChange={e => set('claims_history_json', e.target.value)} />
          </Field>
        </div>

        {error && <div style={{ background: '#fee2e2', border: '1px solid #fca5a5', borderRadius: 8, padding: '1rem', marginBottom: '1rem', color: '#dc2626' }}>{error}</div>}
        <button type="submit" style={s.btn} disabled={loading}>{loading ? 'Processing…' : 'Submit Claim'}</button>
      </form>

      {result && <ResultPanel result={result} nav={nav} />}
    </>
  )
}

// ── File upload mode ──────────────────────────────────────────────────────────
function FileMode() {
  const nav = useNavigate()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [result, setResult] = useState(null)
  const [files, setFiles] = useState([])
  const [form, setForm] = useState({
    member_id: 'EMP001', policy_id: 'PLUM_GHI_2024',
    claim_category: 'CONSULTATION', treatment_date: '',
    claimed_amount: '', hospital_name: '', ytd_claims_amount: '0',
  })

  function set(k, v) { setForm(f => ({ ...f, [k]: v })) }

  async function handleSubmit(e) {
    e.preventDefault()
    if (!files.length) { setError('Please select at least one document file.'); return }
    setLoading(true); setError(null); setResult(null)
    try {
      const fd = new FormData()
      Object.entries(form).forEach(([k, v]) => v && fd.append(k, v))
      files.forEach(f => fd.append('files', f))
      const res = await submitClaimFiles(fd)
      setResult(res)
    } catch (err) { setError(err.message) }
    finally { setLoading(false) }
  }

  return (
    <>
      <div style={{ ...s.card, background: '#fffbeb', border: '1px solid #fcd34d' }}>
        <p style={{ fontSize: 13, color: '#92400e' }}>
          <strong>File Upload Mode</strong> — each uploaded image or PDF is sent to GPT-4o vision for extraction.
          Requires a valid <code>OPENAI_API_KEY</code> in the backend <code>.env</code>.
        </p>
      </div>

      <form onSubmit={handleSubmit}>
        <div style={s.card}>
          <p style={{ fontWeight: 600, marginBottom: '1rem' }}>Member &amp; Claim Details</p>
          <ClaimFields form={form} set={set} />
        </div>

        <div style={s.card}>
          <Field label="Upload Documents (images or PDFs)">
            <input type="file" accept="image/*,.pdf" multiple
              style={{ ...s.input, padding: '6px' }}
              onChange={e => setFiles(Array.from(e.target.files))} />
          </Field>
          {files.length > 0 && (
            <div style={{ marginTop: '.5rem', fontSize: 13, color: '#555' }}>
              {files.map((f, i) => <div key={i} style={{ padding: '3px 0' }}>📄 {f.name} ({(f.size / 1024).toFixed(0)} KB)</div>)}
            </div>
          )}
        </div>

        {error && <div style={{ background: '#fee2e2', border: '1px solid #fca5a5', borderRadius: 8, padding: '1rem', marginBottom: '1rem', color: '#dc2626' }}>{error}</div>}
        <button type="submit" style={s.btn} disabled={loading}>{loading ? 'Uploading & Processing…' : 'Upload & Submit'}</button>
      </form>

      {result && <ResultPanel result={result} nav={nav} />}
    </>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function SubmitClaim() {
  const [mode, setMode] = useState('json')

  const tabStyle = (active) => ({
    padding: '8px 20px', cursor: 'pointer', fontWeight: 600, fontSize: 14,
    borderBottom: active ? '3px solid #7c83fd' : '3px solid transparent',
    color: active ? '#7c83fd' : '#888', background: 'none', border: 'none',
    borderBottom: active ? '3px solid #7c83fd' : '3px solid transparent',
  })

  return (
    <div>
      <h2 style={{ marginBottom: '1rem', fontWeight: 700 }}>Submit Claim</h2>

      <div style={{ display: 'flex', gap: '1rem', borderBottom: '1px solid #e5e7eb', marginBottom: '1.5rem' }}>
        <button style={tabStyle(mode === 'json')} onClick={() => setMode('json')}>Test Cases / JSON</button>
        <button style={tabStyle(mode === 'files')} onClick={() => setMode('files')}>Upload Real Documents</button>
      </div>

      {mode === 'json' ? <JsonMode /> : <FileMode />}
    </div>
  )
}
