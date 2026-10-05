import type { FlagKind } from '../api'

// Flags always show an icon and a text label, never color alone.
const FLAG_LABELS: Record<FlagKind, string> = {
  extraction: 'Unreadable',
  validation: 'Check numbers',
  duplicate: 'Possible duplicate',
  anomaly: 'Unusual charge',
}

export function FlagBadge({ kind }: { kind: FlagKind }) {
  return (
    <span className={`badge badge-${kind}`}>
      <span aria-hidden="true" className="badge-icon">
        !
      </span>
      {FLAG_LABELS[kind]}
    </span>
  )
}
