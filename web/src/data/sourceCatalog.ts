import type { ProviderInfo, ProviderStatus } from '../api/types'

export interface SourceCatalogEntry {
  id: string
  apiId?: string
  name: string
  meta: string
  tone: '' | 'ok' | 'warn'
  group: 'reach' | 'other'
  defaultChecked?: boolean
}

export interface SourceOption {
  id: string
  apiId: string
  name: string
  meta: string
  tone: '' | 'ok' | 'warn' | 'off'
  group: 'reach' | 'other'
  connected: boolean
  providerStatus: ProviderStatus | 'missing' | 'offline'
  defaultChecked: boolean
}

/** Labels stay stable even when a platform is not registered by the backend. */
export const SOURCE_CATALOG: SourceCatalogEntry[] = [
  { id: 'reddit', name: 'Reddit', meta: '可选 · 需登录', tone: 'warn', group: 'reach', defaultChecked: true },
  { id: 'github', name: 'GitHub', meta: '默认 · 免登录', tone: 'ok', group: 'reach' },
  { id: 'youtube', name: 'YouTube', meta: '默认 · 免登录', tone: 'ok', group: 'reach' },
  { id: 'twitter', name: 'Twitter / X', meta: '实验 · 需登录', tone: 'warn', group: 'reach' },
  { id: 'facebook', name: 'Facebook', meta: '实验 · 需登录', tone: 'warn', group: 'reach' },
  { id: 'instagram', name: 'Instagram', meta: '实验 · 需登录', tone: 'warn', group: 'reach' },
  { id: 'bilibili', name: 'Bilibili', meta: '默认 · 需登录', tone: 'warn', group: 'reach' },
  { id: 'xiaohongshu', name: '小红书', meta: '可选 · 需登录', tone: 'warn', group: 'reach' },
  { id: 'linkedin', name: 'LinkedIn', meta: '可选 · 需登录', tone: 'warn', group: 'reach' },
  { id: 'boss', name: 'Boss 直聘', meta: '可选 · 需登录', tone: 'warn', group: 'reach' },
  { id: 'v2ex', name: 'V2EX', meta: '默认 · 免登录', tone: 'ok', group: 'reach' },
  { id: 'xueqiu', name: '雪球', meta: '可选 · 需登录', tone: 'warn', group: 'reach' },
  { id: 'xiaoyuzhou', name: '小宇宙', meta: '可选 · 免登录', tone: 'ok', group: 'reach' },
  { id: 'web', name: 'Web（公开网页）', meta: '默认 · 免登录', tone: 'ok', group: 'reach', defaultChecked: true },
  { id: 'exa', name: '网页搜索（Exa / Tavily）', meta: '需配置 Key', tone: 'warn', group: 'other' },
  { id: 'hn', name: 'Hacker News', apiId: 'hackernews', meta: 'Algolia 公开 API · 免登录', tone: 'ok', group: 'other' },
  { id: 'amazon', name: 'Amazon 商品', apiId: 'amazon.creators', meta: '官方 Creators API · 需 Key', tone: 'warn', group: 'other' },
  { id: 'trends', name: 'Google Trends', apiId: 'google.trends', meta: '选品趋势 · 免登录（可能限流）', tone: 'ok', group: 'other' },
  { id: 'alibaba', name: '1688 / Alibaba', meta: '供应链 · 需官方 Open Platform', tone: 'warn', group: 'other' },
  { id: 'keepa', name: 'Keepa', meta: '需 API Key', tone: 'warn', group: 'other' },
  { id: 'rss', apiId: 'rss', name: 'RSS / 博客', meta: '订阅源 · 需配置', tone: '', group: 'other' },
  { id: 'ph', name: 'Product Hunt', meta: '需 API Token', tone: '', group: 'other' },
]

const UNKNOWN_META = '未接入 Provider API'

export function sourceApiId(entry: SourceCatalogEntry): string {
  return entry.apiId || `agent-reach.${entry.id}`
}

export function mergeSources(
  providers: ProviderInfo[] | undefined,
  online: boolean,
): SourceOption[] {
  const byId = new Map((providers || []).map((provider) => [provider.id, provider]))
  const known = new Set<string>()

  const options: SourceOption[] = SOURCE_CATALOG.map((entry) => {
    const apiId = sourceApiId(entry)
    known.add(apiId)
    const provider = byId.get(apiId)
    const providerStatus: SourceOption['providerStatus'] = !online
      ? 'offline'
      : provider
        ? provider.status
        : 'missing'
    const connected =
      online && Boolean(provider) && ['ready', 'degraded'].includes(provider!.status)
    let meta = entry.meta
    if (!online) {
      meta = 'API 未连接'
    } else if (!provider) {
      meta = UNKNOWN_META
    } else if (!connected) {
      meta = provider.note || providerStatusLabel(provider.status)
    } else if (provider.note) {
      meta = provider.note
    }
    return {
      id: entry.id,
      apiId,
      name: entry.name,
      meta,
      tone: connected ? entry.tone : 'off',
      group: entry.group,
      connected,
      providerStatus,
      defaultChecked: Boolean(entry.defaultChecked),
    }
  })

  for (const provider of providers || []) {
    if (known.has(provider.id)) continue
    const connected = online && ['ready', 'degraded'].includes(provider.status)
    options.push({
      id: provider.id,
      apiId: provider.id,
      name: provider.name,
      meta: `${provider.group} · ${provider.note || '已接入'}`,
      tone: connected ? (provider.status === 'ready' ? 'ok' : 'warn') : 'off',
      group: 'other',
      connected,
      providerStatus: online ? provider.status : 'offline',
      defaultChecked: false,
    })
  }

  return options
}

function providerStatusLabel(status: ProviderStatus): string {
  const labels: Record<ProviderStatus, string> = {
    ready: '可用',
    degraded: '降级可用',
    needs_auth: '需登录',
    disabled: '已停用',
    not_configured: '未配置',
  }
  return labels[status]
}

/**
 * Keep already-selected providers visible even when they are currently
 * unavailable, so editing a schedule never silently drops them.
 */
export function withSelectedSources(
  options: SourceOption[],
  selected: Set<string>,
): SourceOption[] {
  const known = new Set(options.map((option) => option.apiId))
  const extras: SourceOption[] = []
  for (const apiId of selected) {
    if (known.has(apiId)) continue
    extras.push({
      id: apiId,
      apiId,
      name: apiId,
      meta: '未接入 Provider API',
      tone: 'off',
      group: 'other',
      connected: false,
      providerStatus: 'missing',
      defaultChecked: false,
    })
  }
  return [
    ...options.filter(
      (option) => option.connected || selected.has(option.apiId),
    ),
    ...extras,
  ]
}

export function providerName(
  providers: ProviderInfo[] | undefined,
  providerId: string,
): string {
  return providers?.find((provider) => provider.id === providerId)?.name ?? providerId
}
