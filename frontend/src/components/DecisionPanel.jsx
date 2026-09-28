import { useState } from 'react'

const DECISIONS = [
  { key: 'accepted', label: 'Accept preparation', hint: 'The prepared view and recommendation are sound.' },
  { key: 'request_information', label: 'Request information', hint: 'More evidence or clarification is needed.' },
  { key: 'rejected', label: 'Reject preparation', hint: 'The preparation is wrong or unusable.' },
  { key: 'duplicate', label: 'Mark as duplicate', hint: 'Confirm that this claim is a duplicate of the matched claim.' },
]

export default function DecisionPanel({ claim, onDecided }) {
  const [handler, setHandler] = useState('')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const verificationItems = claim.verification_items || []
  const [confirmed, setConfirmed] = useState(claim.verification_confirmations || [])
  const [editing, setEditing] = useState(false)

  const decided = claim.status && !['prepared', 'awaiting_verification', 'processing', 'duplicate_pending'].includes(claim.status)

  const submit = async (decision) => {
    if (!handler.trim()) { setError('Enter your name: decisions are never anonymous.'); return }
    if (confirmed.length !== verificationItems.length) {
      setError('Confirm every highlighted field against its source document before deciding.')
      return
    }
    setBusy(true); setError(null)
    try {
      const response = await fetch(`/api/claims/${claim.claim_id}/decision`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ decision, handler, note, verification_confirmations: confirmed }),
      })
      if (!response.ok) throw new Error((await response.json()).detail || response.statusText)
      onDecided?.()
    } catch (err) {
      setError(String(err))
    } finally {
      setBusy(false)
    }
  }

  const archive = async () => {
    setBusy(true); setError(null)
    try {
      const response = await fetch(`/api/claims/${claim.claim_id}/archive`, { method: 'POST' })
      if (!response.ok) throw new Error((await response.json()).detail || response.statusText)
      onDecided?.()
    } catch (err) { setError(String(err)) } finally { setBusy(false) }
  }

  const beginEdit = () => {
    setHandler(claim.handler || '')
    setNote(claim.handler_note || '')
    setConfirmed(claim.verification_confirmations || [])
    setEditing(true)
  }

  if (decided && !editing) {
    return (
      <section className="decision done">
        <h3>Handler decision</h3>
        <p>
          <strong className={`status status-${claim.status}`}>{claim.status.replaceAll('_', ' ')}</strong>
          {' '}by {claim.handler} at {claim.decided_at}
        </p>
        {claim.handler_note && <p className="muted">“{claim.handler_note}”</p>}
        <div className="decision-buttons">
          <button onClick={beginEdit}>Edit decision</button>
          {['accepted', 'request_information', 'rejected', 'duplicate'].includes(claim.status) && <button className="secondary" onClick={archive} disabled={busy}>Archive</button>}
        </div>
      </section>
    )
  }

  if (claim.status === 'duplicate') {
    return (
      <section className="decision done">
        <h3>Duplicate claim</h3>
        <p>This claim matches {claim.duplicate_of || 'an existing claim'} and cannot receive a handler decision.</p>
      </section>
    )
  }

  return (
    <section className="decision">
      <h3>Handler decision</h3>
      <p className="muted">
        The workspace prepares and recommends. Approving, declining or paying a claim stays with
        authorised staff outside this tool.
      </p>
      <div className="row">
        <input
          placeholder="Your name"
          value={handler}
          onChange={(e) => setHandler(e.target.value)}
        />
      </div>
      <textarea
        placeholder="Note (what you checked, what you changed)"
        value={note}
        onChange={(e) => setNote(e.target.value)}
        rows={3}
      />
      {verificationItems.length > 0 && (
        <div className="verification-checklist">
          <strong>Required field verification</strong>
          {verificationItems.map((item) => (
            <label key={item.id}>
              <input
                type="checkbox"
                checked={confirmed.includes(item.id)}
                onChange={(event) => setConfirmed((current) => event.target.checked
                  ? [...current, item.id]
                  : current.filter((id) => id !== item.id))}
              />
              Confirm <b>{item.field.replaceAll('_', ' ')}</b> = {String(item.value ?? 'missing')} from {item.document.replaceAll('_', ' ')} ({Number(item.confidence).toFixed(2)})
            </label>
          ))}
        </div>
      )}
      {error && <div className="banner error">{error}</div>}
      <div className="decision-buttons">
        {DECISIONS.filter((d) => d.key !== 'duplicate' || claim.status === 'duplicate_pending' || claim.status === 'duplicate' || claim.duplicate_of).map((d) => (
          <button
            key={d.key}
            disabled={busy}
            title={d.hint}
            className={d.key === 'rejected' || d.key === 'duplicate' ? 'danger' : ''}
            onClick={() => submit(d.key)}
          >
            {d.label}
          </button>
        ))}
      </div>
    </section>
  )
}
