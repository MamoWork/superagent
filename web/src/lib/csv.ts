function escapeCell(value: unknown): string {
  return `"${String(value ?? '').replace(/"/g, '""')}"`
}

export function toCsv(rows: unknown[][]): string {
  return rows.map((row) => row.map(escapeCell).join(',')).join('\n')
}

export function downloadCsv(filename: string, rows: unknown[][]): void {
  const blob = new Blob(['\uFEFF' + toCsv(rows)], {
    type: 'text/csv;charset=utf-8',
  })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 1_500)
}
