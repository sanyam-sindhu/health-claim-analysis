import React from 'react'
import { Routes, Route, Link, useLocation } from 'react-router-dom'
import SubmitClaim from './pages/SubmitClaim.jsx'
import ClaimsList from './pages/ClaimsList.jsx'
import ClaimDetail from './pages/ClaimDetail.jsx'

const NAV = [
  { to: '/', label: 'Submit Claim' },
  { to: '/claims', label: 'All Claims' },
]

export default function App() {
  const loc = useLocation()

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <header style={{ background: '#1a1a2e', color: '#fff', padding: '0 2rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '2rem', height: 56 }}>
          <span style={{ fontWeight: 700, fontSize: 18, letterSpacing: 1 }}>🌿 Plum Claims</span>
          {NAV.map(n => (
            <Link key={n.to} to={n.to} style={{
              color: loc.pathname === n.to ? '#7c83fd' : '#ccc',
              textDecoration: 'none', fontWeight: 500, fontSize: 14,
            }}>{n.label}</Link>
          ))}
        </div>
      </header>

      <main style={{ flex: 1, padding: '2rem', maxWidth: 960, margin: '0 auto', width: '100%' }}>
        <Routes>
          <Route path="/" element={<SubmitClaim />} />
          <Route path="/claims" element={<ClaimsList />} />
          <Route path="/claims/:id" element={<ClaimDetail />} />
        </Routes>
      </main>
    </div>
  )
}
