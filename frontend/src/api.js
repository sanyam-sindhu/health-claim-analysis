const BASE = (import.meta.env.VITE_API_URL || '') + '/api'

export async function submitClaim(payload) {
  const res = await fetch(`${BASE}/claims`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Submission failed')
  }
  return res.json()
}

export async function submitClaimFiles(formData) {
  const res = await fetch(`${BASE}/claims/upload`, { method: 'POST', body: formData })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Upload failed')
  }
  return res.json()
}

export async function listClaims() {
  const res = await fetch(`${BASE}/claims`)
  if (!res.ok) throw new Error('Failed to fetch claims')
  return res.json()
}

export async function getClaim(claimId) {
  const res = await fetch(`${BASE}/claims/${claimId}`)
  if (!res.ok) throw new Error('Claim not found')
  return res.json()
}
