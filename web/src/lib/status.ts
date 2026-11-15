import type {
  ProviderStatus,
  RunStatus,
  SavedStage,
  Verdict,
} from '../api/types'

export interface ToneMeta {
  tone: 'high' | 'verify' | 'red' | 'ghost'
  label: string
}

export function verdictMeta(verdict: Verdict): ToneMeta {
  if (verdict === 'build') return { tone: 'high', label: '建议投入' }
  if (verdict === 'verify') return { tone: 'verify', label: '待验证' }
  return { tone: 'red', label: '放弃' }
}

export function scoreColor(score: number): string {
  if (score >= 80) return '#059669'
  if (score >= 60) return '#d97706'
  return '#dc2626'
}

export const STAGES: Array<{
  id: SavedStage
  label: string
  short: string
}> = [
  { id: 'saved', label: '待验证', short: '发现机会' },
  { id: 'validating', label: '验证中', short: '进入验证' },
  { id: 'contacted', label: '已触达', short: '已触达' },
  { id: 'replied', label: '跟进中', short: '已回复' },
  { id: 'won', label: '已转化', short: '已转化' },
  { id: 'dropped', label: '已放弃', short: '已放弃' },
]

export function stageLabel(stage: SavedStage): string {
  return STAGES.find((item) => item.id === stage)?.label ?? stage
}

export function providerStatusLabel(status: ProviderStatus | 'missing' | 'offline'): string {
  if (status === 'ready') return '可用'
  if (status === 'degraded') return '降级可用'
  if (status === 'needs_auth') return '需登录'
  if (status === 'disabled') return '已停用'
  if (status === 'not_configured') return '未配置'
  if (status === 'offline') return 'API 未连接'
  return '未接入'
}

export function runStatusMeta(status: RunStatus): {
  className: 'done' | 'empty'
  label: string
} {
  if (status === 'completed') return { className: 'done', label: '完成' }
  if (status === 'partial') return { className: 'empty', label: '部分完成' }
  if (status === 'failed') return { className: 'empty', label: '失败' }
  return { className: 'empty', label: '运行中' }
}
