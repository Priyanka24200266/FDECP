function Metric({ label, value, claimIds = [], onSelect }) {
  return (
    <button className="metric" onClick={() => claimIds[0] && onSelect(claimIds[0])} disabled={!claimIds.length}>
      <span className="metric-label">{label}</span>
      <strong>{value}</strong>
      <small>{claimIds.length ? `${claimIds.length} claim${claimIds.length === 1 ? '' : 's'}` : 'none'}</small>
    </button>
  )
}

export default function MetricsOverview({ metrics, onSelect }) {
  if (!metrics || metrics.processed_claims === 0) return null
  const waiting = metrics.waiting_on_policyholder || { count: 0, claim_ids: [] }
  const senior = metrics.needs_senior_adjuster || { count: 0, claim_ids: [] }
  const cleared = metrics.cleared_without_finding || { count: 0, claim_ids: [] }
  return (
    <section className="metrics-overview">
      <div className="metrics-heading">
        <div><h2>Operations overview</h2><span className="muted">{metrics.processed_claims} processed claims</span></div>
        <span className="muted">Average preparation: {metrics.average_prepare_seconds == null ? '—' : `${metrics.average_prepare_seconds.toFixed(1)}s`}</span>
      </div>
      <div className="metrics-grid">
        <Metric label="Waiting on policyholder" value={waiting.count} claimIds={waiting.claim_ids} onSelect={onSelect} />
        <Metric label="Needs senior adjuster" value={senior.count} claimIds={senior.claim_ids} onSelect={onSelect} />
        <Metric label="Cleared without finding" value={cleared.count} claimIds={cleared.claim_ids} onSelect={onSelect} />
        {Object.entries(metrics.recommendation_mix || {}).map(([name, value]) => (
          <Metric key={name} label={`Recommendation: ${name.replaceAll('_', ' ')}`} value={value.count} claimIds={value.claim_ids} onSelect={onSelect} />
        ))}
      </div>
    </section>
  )
}