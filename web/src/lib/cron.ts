export const CRON_PRESETS = [
  { value: '0 9 * * *', label: '每天 09:00' },
  { value: '0 */6 * * *', label: '每 6 小时' },
  { value: '0 9 * * 1', label: '每周一 09:00' },
] as const

const LABELS: Record<string, string> = Object.fromEntries(
  CRON_PRESETS.map((preset) => [preset.value, preset.label]),
)

export function cronLabel(cron: string): string {
  return LABELS[cron] ?? cron
}

export function nextRunSortValue(value: string | null): string {
  if (!value) return '9999-12-31T23:59:59'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '9999-12-31T23:59:59' : date.toISOString()
}
