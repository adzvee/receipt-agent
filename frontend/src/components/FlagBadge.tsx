import type { Flag, FlagKind } from '../api'

// Flags always show an icon and a text label, never color alone.
const KIND_LABELS: Record<FlagKind, string> = {
  extraction: 'Unreadable',
  validation: 'Check numbers',
  duplicate: 'Possible duplicate',
  anomaly: 'Unusual charge',
}

// Checks that deserve a more specific label than their kind.
const CODE_LABELS: Record<string, string> = {
  high_tip: 'Unusual tip',
}

type FlagSummary = Pick<Flag, 'kind' | 'code'>

function flagLabel(flag: FlagSummary): string {
  return CODE_LABELS[flag.code] ?? KIND_LABELS[flag.kind]
}

export function FlagBadge({ flag }: { flag: FlagSummary }) {
  return (
    <span className={`badge badge-${flag.kind}`}>
      <span aria-hidden="true" className="badge-icon">
        !
      </span>
      {flagLabel(flag)}
    </span>
  )
}

/** A receipt's open (not dismissed) flags, one badge per distinct label. */
export function OpenFlagBadges({ flags }: { flags: Flag[] }) {
  const byLabel = new Map<string, Flag>()
  for (const flag of flags) {
    if (!flag.dismissed_at && !byLabel.has(flagLabel(flag))) byLabel.set(flagLabel(flag), flag)
  }
  return (
    <span className="badge-row">
      {[...byLabel].map(([label, flag]) => (
        <FlagBadge key={label} flag={flag} />
      ))}
    </span>
  )
}
