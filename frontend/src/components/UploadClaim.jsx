import { useEffect, useRef, useState } from 'react'

export default function UploadClaim({ onSubmitted, initialClaimId = '' }) {
  const [claimId, setClaimId] = useState(initialClaimId)
  const [files, setFiles] = useState([])
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState(null)
  const [error, setError] = useState(null)
  const panelRef = useRef(null)
  const claimInputRef = useRef(null)

  useEffect(() => {
    setClaimId(initialClaimId)
    if (initialClaimId) {
      panelRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' })
      window.setTimeout(() => claimInputRef.current?.focus(), 250)
    }
  }, [initialClaimId])

  const submit = async (event) => {
    event.preventDefault()
    if (!claimId.trim() || files.length === 0) {
      setError('Enter a claim ID and select at least one PDF or image.')
      return
    }
    setBusy(true); setError(null); setMessage(null)
    const body = new FormData()
    body.append('claim_id', claimId.trim())
    files.forEach((file) => body.append('files', file))
    try {
      const response = await fetch('/api/claims/submit', { method: 'POST', body })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || response.statusText)
      setMessage(`${data.claim_id} submitted and processing started.`)
      setFiles([])
      event.target.reset()
      onSubmitted?.()
    } catch (err) {
      setError(String(err))
    } finally {
      setBusy(false)
    }
  }

  const reset = () => { setClaimId(''); setFiles([]); setMessage(null); setError(null) }

  return (
    <section className="upload-panel" ref={panelRef}>
      <div>
        <h2>Submit claim evidence</h2>
        <p className="muted">Upload documents and photographs for a new claim or add evidence to an existing one.</p>
      </div>
      <form onSubmit={submit} className="upload-form">
        <input
          aria-label="Claim ID"
          ref={claimInputRef}
          placeholder="Claim ID, e.g. CLM-2026-0436"
          value={claimId}
          onChange={(event) => setClaimId(event.target.value)}
          maxLength={40}
        />
        <input
          aria-label="Claim evidence files"
          type="file"
          accept=".pdf,.png,.jpg,.jpeg,.webp"
          multiple
          onChange={(event) => setFiles(Array.from(event.target.files || []))}
        />
        <button type="submit" disabled={busy}>{busy ? 'Submitting…' : 'Upload and process'}</button>
        {initialClaimId && <button type="button" className="secondary" onClick={reset}>Clear claim</button>}
      </form>
      {files.length > 0 && <span className="muted">{files.length} file{files.length === 1 ? '' : 's'} selected</span>}
      {message && <div className="banner success">{message}</div>}
      {error && <div className="banner error">{error}</div>}
    </section>
  )
}
