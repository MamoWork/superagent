import { describe, expect, it } from 'vitest'
import type { ProviderInfo } from '../api/types'
import {
  mergeSources,
  providerName,
  withSelectedSources,
} from './sourceCatalog'

const reddit: ProviderInfo = {
  id: 'agent-reach.reddit',
  name: 'Reddit',
  group: 'agent-reach',
  capabilities: ['search'],
  auth: 'browser',
  status: 'ready',
  cost: 'free',
  rate_limit: { requests_per_minute: 10 },
  note: null,
}

const amazon: ProviderInfo = {
  id: 'amazon.creators',
  name: 'Amazon Creators',
  group: 'marketplace',
  capabilities: ['search'],
  auth: 'api_key',
  status: 'not_configured',
  cost: 'byo_key',
  rate_limit: null,
  note: '缺少 API Key',
}

describe('mergeSources', () => {
  it('marks every source disconnected while offline', () => {
    const sources = mergeSources([reddit], false)
    expect(sources.every((source) => !source.connected)).toBe(true)
    expect(sources.every((source) => source.meta === 'API 未连接')).toBe(true)
    expect(sources.every((source) => source.providerStatus === 'offline')).toBe(true)
  })

  it('only enables ready or degraded providers', () => {
    const sources = mergeSources([reddit, amazon], true)
    const redditSource = sources.find((source) => source.apiId === reddit.id)
    const amazonSource = sources.find((source) => source.apiId === amazon.id)
    expect(redditSource?.connected).toBe(true)
    expect(amazonSource?.connected).toBe(false)
    expect(amazonSource?.meta).toBe('缺少 API Key')
  })

  it('keeps catalog labels for providers the backend has not registered', () => {
    const sources = mergeSources([], true)
    const rss = sources.find((source) => source.id === 'rss')
    expect(rss?.connected).toBe(false)
    expect(rss?.meta).toBe('未接入 Provider API')
    expect(rss?.providerStatus).toBe('missing')
  })

  it('matches the registered RSS provider to its catalog entry', () => {
    const rss: ProviderInfo = {
      ...reddit,
      id: 'rss',
      name: 'RSS / 博客',
      group: 'rss',
      status: 'not_configured',
      note: '设置 OPPORTUNITY_RSS_FEEDS 后启用',
    }
    const sources = mergeSources([rss], true)
    const matches = sources.filter((source) => source.name === 'RSS / 博客')
    expect(matches).toHaveLength(1)
    expect(matches[0].apiId).toBe('rss')
    expect(matches[0].meta).toBe('设置 OPPORTUNITY_RSS_FEEDS 后启用')
  })

  it('appends providers that are not in the catalog', () => {
    const custom: ProviderInfo = {
      ...reddit,
      id: 'custom.feed',
      name: 'Custom feed',
      group: 'rss',
      status: 'degraded',
    }
    const sources = mergeSources([reddit, custom], true)
    const appended = sources.find((source) => source.apiId === 'custom.feed')
    expect(appended?.name).toBe('Custom feed')
    expect(appended?.connected).toBe(true)
    expect(appended?.group).toBe('other')
  })

  it('falls back to the provider id when a display name is unknown', () => {
    expect(providerName(undefined, 'agent-reach.web')).toBe('agent-reach.web')
    expect(providerName([reddit], reddit.id)).toBe('Reddit')
  })
})

describe('withSelectedSources', () => {
  it('keeps a selected provider that is no longer available', () => {
    const options = mergeSources([reddit, amazon], true)
    const visible = withSelectedSources(options, new Set([amazon.id]))
    const kept = visible.find((source) => source.apiId === amazon.id)
    expect(kept).toBeDefined()
    expect(kept?.connected).toBe(false)
  })

  it('keeps a selected provider that is no longer registered', () => {
    const options = mergeSources([reddit], true)
    const visible = withSelectedSources(options, new Set(['old.provider']))
    const kept = visible.find((source) => source.apiId === 'old.provider')
    expect(kept?.connected).toBe(false)
    expect(kept?.meta).toBe('未接入 Provider API')
  })

  it('hides unselected unavailable providers', () => {
    const options = mergeSources([reddit, amazon], true)
    const visible = withSelectedSources(options, new Set([reddit.id]))
    expect(visible.some((source) => source.apiId === amazon.id)).toBe(false)
  })
})
