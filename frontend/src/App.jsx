import { useEffect, useState, useCallback } from 'react'
import ClaimList from './components/ClaimList.jsx'
import ClaimDetail from './components/ClaimDetail.jsx'
import MetricsOverview from './components/MetricsOverview.jsx'
import UploadClaim from './components/UploadClaim.jsx'

export default function App() {
  const [claims, setClaims] = useState([])
  const [selected, setSelected] = useState(null)
  const [health, setHealth] = useState(null)
  const [error, setError] = useState(null)
  const [metrics, setMetrics] = useState(null)
  const [uploadClaimId, setUploadClaimId] = useState('')
  const [initialLoading, setInitialLoading] = useState(true)
  const [processingClaims, setProcessingClaims] = useState([])

  const loadClaims = useCallback(async () => {
    try {
      const response = await fetch('/api/claims')
      if (!response.ok) throw new Error(`claims: ${response.status}`)
      const data = await response.json()
      const activeProcessing = data.processing || []
      setProcessingClaims(activeProcessing)
      setClaims(data.claims.map((claim) => activeProcessing.includes(claim.claim_id)
        ? { ...claim, status: 'processing' }
        : claim))
      setError(null)
      return data
    } catch (err) {
      setError(String(err))
      return null
    } finally {
      setInitialLoading(false)
    }
  }, [])

  const loadMetrics = async () => {
    try {
      const response = await fetch('/api/metrics')
      if (response.ok) setMetrics(await response.json())
    } catch (_) {
      // The claim workspace remains usable when the optional overview is unavailable.
    }
  }

  useEffect(() => {
    fetch('/api/health').then(r => r.json()).then(setHealth).catch(() => {})
    loadClaims()
    loadMetrics()
  }, [loadClaims])

  // While anything is processing, poll so the list updates on its own.
  useEffect(() => {
    const anyProcessing = claims.some(c => c.status === 'processing')
    if (!anyProcessing) return undefined
    const timer = setInterval(loadClaims, 4000)
    return () => clearInterval(timer)
  }, [claims, loadClaims])

  const processClaim = async (claimId) => {
    if (processingClaims.includes(claimId)) return
    setClaims(cs => cs.map(c => (c.claim_id === claimId ? { ...c, status: 'processing' } : c)))
    setProcessingClaims((current) => current.includes(claimId) ? current : [...current, claimId])
    try {
      const response = await fetch(`/api/claims/${claimId}/process`, { method: 'POST' })
      if (!response.ok) throw new Error(`Could not process ${claimId}: ${response.status}`)
    } catch (err) {
      setError(String(err))
      setProcessingClaims((current) => current.filter((id) => id !== claimId))
      loadClaims()
    }
    loadClaims(); loadMetrics()
  }

  const submitted = () => { loadClaims(); loadMetrics() }

  return (
    <div className="app">
      <header>
        <div>
          <h1>Contoso Claims Workspace</h1>
          <p className="sub">
            Motor claim intake and review. Prepared automatically, decided by a handler.
          </p>
        </div>
        {health && (
          <div className="health">
            <span className="pill">{health.alias}</span>
            <span className="muted">{claims.filter((claim) => ['prepared', 'awaiting_verification'].includes(claim.status)).length} prepared</span>
          </div>
        )}
      </header>

      {error && <div className="banner error">Cannot reach the API: {error}</div>}
      {initialLoading && <div className="banner loading">Loading claims workspace and operational metrics…</div>}
      {processingClaims.length > 0 && (
        <div className="banner loading">
          Processing {processingClaims.join(', ')}. Backend extraction and validation are running; this may take several minutes.
        </div>
      )}

      <UploadClaim initialClaimId={uploadClaimId} onSubmitted={() => { setUploadClaimId(''); submitted() }} />
      <MetricsOverview metrics={metrics} onSelect={setSelected} />

      <div className="layout">
        <ClaimList
          claims={claims}
          selected={selected}
          onSelect={setSelected}
          onProcess={processClaim}
          processingClaims={processingClaims}
          onUpload={setUploadClaimId}
        />
        <ClaimDetail claimId={selected} onDecided={() => { loadClaims(); loadMetrics() }} />
      </div>

      <footer>
        Training environment. Contoso Insurance is fictional. This workspace never approves,
        declines or pays a claim (CIP-CLM-200 section 5.2).
      </footer>
    </div>
  )
}
