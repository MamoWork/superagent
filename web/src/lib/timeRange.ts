/** The backend uses null for "no time limit"; 0 is not a valid API value. */
export function toTimeRangeDays(value: string): number | null {
  const parsed = Number(value)
  if (!Number.isFinite(parsed) || parsed === 0) return null
  return parsed
}
