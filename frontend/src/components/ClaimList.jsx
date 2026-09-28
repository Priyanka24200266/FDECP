const RECOMMENDATION_LABEL = {
  proceed: 'Proceed',
  request_information: 'Request info',
  refer: 'Refer',
}

import { useState } from 'react'

const SECTIONS = [
  { key: 'active', title: 'Awaiting handler decision', statuses: ['prepared', 'awaiting_verification', 'processing', 'not_processed'] },
  { key: 'accepted', title: 'Accepted preparations', statuses: ['accepted'] },
  { key: 'request_information', title: 'Request information', statuses: ['request_information', 'amended'] },
  { key: 'rejected', title: 'Rejected preparations', statuses: ['rejected'] },
  { key: 'archived', title: 'Archive', statuses: ['archived'] },
  { key: 'duplicate_pending', title: 'Potential duplicates · handler review', statuses: ['duplicate_pending'] },
  { key: 'duplicate', title: 'Confirmed duplicate claims', statuses: ['duplicate'] },
]

function ClaimCard({ claim, selected, onSelect, onProcess, onUpload, processingClaims }) {
  const isSelected = claim.claim_id === selected
  const rec = claim.agent_recommendation
  const canUpload = ['request_information', 'amended'].includes(claim.status)
  const canReprocess = ['prepared', 'awaiting_verification', 'accepted', 'request_information', 'amended', 'rejected'].includes(claim.status)
  return (
    <div className={`claim-card ${isSelected ? 'selected' : ''}`} onClick={() => onSelect(claim.claim_id)}>
      <div className="row">
        <strong>{claim.claim_id}</strong>
        {rec && <span className={`rec rec-${rec}`}>{RECOMMENDATION_LABEL[rec] || rec}</span>}
      </div>
      {claim.status === 'not_processed' && <div className="row"><span className="muted">Not processed</span><button disabled={processingClaims.includes(claim.claim_id)} onClick={(e) => { e.stopPropagation(); onProcess(claim.claim_id) }}>Process</button></div>}
      {claim.status === 'prepared' && <div className="processed-label">Processed and ready for handler review</div>}
      {canReprocess && <div className="row reprocess-row"><span className="muted">Already processed</span><button className="secondary" disabled={processingClaims.includes(claim.claim_id)} onClick={(e) => { e.stopPropagation(); onProcess(claim.claim_id) }}>Process again</button></div>}
      {claim.status && !['not_processed', 'processing', 'prepared', 'accepted', 'request_information', 'amended', 'rejected', 'archived', 'duplicate_pending', 'duplicate'].includes(claim.status) && <div className="row"><span className="muted">Awaiting review</span></div>}
      {claim.status === 'processing' && <div className="muted">Processing…</div>}
      {['duplicate_pending', 'duplicate'].includes(claim.status) && <div className="duplicate-warning">Matches {claim.duplicate_of || 'an existing claim'}{claim.status === 'duplicate_pending' ? ' · handler review required' : ' · confirmed duplicate'}</div>}
      {canUpload && <button className="secondary full-button" onClick={(e) => { e.stopPropagation(); onUpload(claim.claim_id) }}>Upload missing information</button>}
      {claim.finding_count != null && <div className="muted">{claim.critical_count > 0 && <span className="critical-dot" title="critical findings" />}{claim.finding_count} finding{claim.finding_count === 1 ? '' : 's'}</div>}
    </div>
  )
}

export default function ClaimList({ claims, selected, onSelect, onProcess, onUpload, processingClaims = [] }) {
  const [expanded, setExpanded] = useState({ active: true })
  return (
    <aside className="claim-list">
      {SECTIONS.map((section) => {
        const sectionClaims = claims.filter((claim) => section.statuses.includes(claim.status))
        return <section className="claim-section" key={section.key}>
          <button className="section-toggle" onClick={() => setExpanded((current) => ({ ...current, [section.key]: !current[section.key] }))}>
            <span>{expanded[section.key] ? '▾' : '▸'} {section.title}</span><span>{sectionClaims.length}</span>
          </button>
          {expanded[section.key] && sectionClaims.map((claim) => <ClaimCard key={claim.claim_id} {...{ claim, selected, onSelect, onProcess, onUpload, processingClaims }} />)}
          {expanded[section.key] && sectionClaims.length === 0 && <p className="muted empty-section">No claims</p>}
        </section>
      })}
    </aside>
  )
}
