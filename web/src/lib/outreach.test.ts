import { describe, expect, it } from 'vitest'
import type { SavedOpportunity } from '../api/types'
import { buildOutreachTemplate } from './outreach'

const opportunity: SavedOpportunity = {
  run_id: 'run_test',
  direction: '跨境宠物用品',
  domain_pack: 'crossborder',
  title: '宠物饮水机清洁配件',
  one_liner: '用户抱怨饮水机难清洗',
  thesis: '清洁配件是重复购买',
  score: 82,
  verdict: 'build',
  target_customer: '宠物用品独立卖家',
  willingness_to_pay: '中等',
  risks: [],
  next_actions: [],
  dimension_scores: [],
  citations: [
    {
      signal_id: 'sig_1',
      source_url: 'https://www.reddit.com/r/cats/comments/example',
      quote: 'I dread cleaning it every week.',
      note: '',
    },
  ],
  stage: 'saved',
  notes: '',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}

describe('buildOutreachTemplate', () => {
  it.each(['direct', 'formal', 'casual'] as const)(
    'includes the real citation and the manual disclaimer (%s)',
    (tone) => {
      const text = buildOutreachTemplate(opportunity, tone)
      expect(text).toContain('https://www.reddit.com/r/cats/comments/example')
      expect(text).toContain('I dread cleaning it every week.')
      expect(text.toLowerCase()).toContain('manual')
    },
  )

  it('falls back to the opportunity itself when there is no citation', () => {
    const text = buildOutreachTemplate(
      { ...opportunity, citations: [] },
      'direct',
    )
    expect(text).toContain(opportunity.one_liner.toLowerCase())
    expect(text).not.toContain('undefined')
  })
})
