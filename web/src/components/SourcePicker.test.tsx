import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { SourceOption } from '../data/sourceCatalog'
import { SourcePicker } from './SourcePicker'

function option(overrides: Partial<SourceOption>): SourceOption {
  return {
    id: 'reddit',
    apiId: 'agent-reach.reddit',
    name: 'Reddit',
    meta: '默认 · 免登录',
    tone: 'ok',
    group: 'reach',
    connected: true,
    providerStatus: 'ready',
    defaultChecked: false,
    ...overrides,
  }
}

const web = option({
  id: 'web',
  apiId: 'agent-reach.web',
  name: 'Web（公开网页）',
})

const amazon = option({
  id: 'amazon',
  apiId: 'amazon.creators',
  name: 'Amazon 商品',
  connected: false,
  providerStatus: 'not_configured',
  meta: '缺少 API Key',
  tone: 'off',
  group: 'other',
})

describe('SourcePicker', () => {
  it('only lets connected providers be selected', () => {
    render(
      <SourcePicker
        options={[option({}), web, amazon]}
        selected={new Set(['agent-reach.reddit'])}
        onChange={() => {}}
      />,
    )

    expect(screen.getByLabelText(/Reddit/)).toBeEnabled()
    expect(screen.getByLabelText(/Reddit/)).toBeChecked()
    expect(screen.getByLabelText(/Amazon/)).toBeDisabled()
    expect(screen.getByLabelText(/Amazon/)).not.toBeChecked()
    expect(screen.getByText('缺少 API Key')).toBeInTheDocument()
  })

  it('adds and removes providers from the current selection', () => {
    const onChange = vi.fn()
    render(
      <SourcePicker
        options={[option({}), web, amazon]}
        selected={new Set(['agent-reach.reddit'])}
        onChange={onChange}
      />,
    )

    fireEvent.click(screen.getByLabelText(/Web（公开网页）/))
    expect(Array.from(onChange.mock.calls[0][0] as Set<string>)).toEqual([
      'agent-reach.reddit',
      'agent-reach.web',
    ])

    onChange.mockClear()
    fireEvent.click(screen.getByLabelText(/Reddit/))
    expect(Array.from(onChange.mock.calls[0][0] as Set<string>)).toEqual([])
  })

  it('selects all available providers and clears them again', () => {
    const onChange = vi.fn()
    render(
      <SourcePicker
        options={[option({}), web, amazon]}
        selected={new Set()}
        onChange={onChange}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: '全选可用来源' }))
    expect(Array.from(onChange.mock.calls[0][0] as Set<string>)).toEqual([
      'agent-reach.reddit',
      'agent-reach.web',
    ])
  })

  it('deselects when every available provider is already selected', () => {
    const onChange = vi.fn()
    render(
      <SourcePicker
        options={[option({}), web, amazon]}
        selected={new Set(['agent-reach.reddit', 'agent-reach.web'])}
        onChange={onChange}
      />,
    )

    expect(screen.getByText('已选 2 个')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '全选可用来源' }))
    expect((onChange.mock.calls[0][0] as Set<string>).size).toBe(0)
  })
})
