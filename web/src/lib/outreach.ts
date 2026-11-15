import type { SavedOpportunity } from '../api/types'

export type OutreachTone = 'direct' | 'formal' | 'casual'

export const OUTREACH_TONES: Array<{ value: OutreachTone; label: string }> = [
  { value: 'direct', label: '简短、直接（推荐）' },
  { value: 'formal', label: '专业、正式' },
  { value: 'casual', label: '轻松、同行交流' },
]

export function buildOutreachTemplate(
  opportunity: SavedOpportunity,
  tone: OutreachTone,
): string {
  const source = opportunity.citations[0]
  const quote = source?.quote?.trim()
  const target = opportunity.target_customer || '你的目标用户'
  const problem = opportunity.one_liner || opportunity.title
  const reference = quote
    ? `I saw your public post${source?.source_url ? ` (${source.source_url})` : ''} where you mentioned: “${quote.slice(0, 180)}”`
    : `I came across your public post while researching ${problem}`

  if (tone === 'formal') {
    return `Hello,

${reference}

I am researching how ${target} handle this problem. ${problem ? `The recurring theme is: ${problem}.` : ''} I am talking with a small number of practitioners to understand the current workflow, the cost of the problem, and what a useful solution would need to do.

Would you be open to a 15-minute conversation? I am not asking you to buy anything; I would value your direct feedback. If it is not relevant, no reply is needed.

Best regards,
[Your name]
[Your contact details]

— This is a manually written template, not an AI-generated message. Send it yourself on the platform and follow its anti-spam rules.`
  }

  if (tone === 'casual') {
    return `Hey — ${reference}

I'm digging into this space and trying to understand how people actually deal with it day to day${opportunity.thesis ? `: ${opportunity.thesis}` : '.'} Not selling anything right now — I'd just like to hear what's annoying about the current setup and what you've already tried.

Open to a quick 10-minute chat this week? Happy to share what I'm learning either way.

[Your name]

— Manual template, not AI-generated. Copy it and send yourself; do not mass-message.`
  }

  return `Hi — ${reference}

I'm researching ${problem.toLowerCase()} for ${target}. I'm trying to understand whether this is a real, recurring cost — and what people currently do instead.

Would you be open to a 10-minute call? No pitch; I'm looking for honest feedback, and I'll keep it short.

[Your name]

— Manual template, not AI-generated. Send it yourself and respect platform rate limits.`
}
