import { describe, expect, it } from 'vitest'
import { cronLabel, nextRunSortValue } from './cron'
import { toTimeRangeDays } from './timeRange'

describe('toTimeRangeDays', () => {
  it('maps the "no limit" option to null', () => {
    expect(toTimeRangeDays('0')).toBeNull()
  })

  it('keeps real day ranges', () => {
    expect(toTimeRangeDays('30')).toBe(30)
    expect(toTimeRangeDays('365')).toBe(365)
  })

  it('does not send NaN for malformed input', () => {
    expect(toTimeRangeDays('')).toBeNull()
    expect(toTimeRangeDays('abc')).toBeNull()
  })
})

describe('cron helpers', () => {
  it('labels known presets and passes custom cron through', () => {
    expect(cronLabel('0 9 * * *')).toBe('每天 09:00')
    expect(cronLabel('*/15 * * * *')).toBe('*/15 * * * *')
  })

  it('sorts empty and invalid next-run values last', () => {
    const empty = nextRunSortValue(null)
    const invalid = nextRunSortValue('not-a-date')
    expect(empty).toBe(invalid)
    expect(empty > nextRunSortValue('2026-01-01T00:00:00Z')).toBe(true)
  })
})
