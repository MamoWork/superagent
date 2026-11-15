import type { ReactNode } from 'react'
import type { Verdict } from '../api/types'
import { verdictMeta } from '../lib/status'

export function VerdictBadge({ verdict }: { verdict: Verdict }) {
  const meta = verdictMeta(verdict)
  return <span className={`badge ${meta.tone}`}>{meta.label}</span>
}

export function Badge({
  children,
  tone = 'ghost',
}: {
  children: ReactNode
  tone?: 'high' | 'verify' | 'red' | 'ghost'
}) {
  return <span className={`badge ${tone}`}>{children}</span>
}
