import type { SourceOption } from '../data/sourceCatalog'

interface SourcePickerProps {
  options: SourceOption[]
  selected: Set<string>
  onChange: (next: Set<string>) => void
}

function SourceGroup({
  title,
  options,
  selected,
  onChange,
}: {
  title: string
  options: SourceOption[]
  selected: Set<string>
  onChange: (next: Set<string>) => void
}) {
  if (!options.length) return null
  return (
    <>
      <div className="source-group-title">{title}</div>
      <div className={`source-grid${title.includes('Agent') ? ' source-grid-wide' : ''}`}>
        {options.map((option) => {
          const checked = option.connected && selected.has(option.apiId)
          return (
            <label
              className={`source-opt${option.connected ? '' : ' is-off'}`}
              key={option.id}
              title={option.connected ? '' : option.meta}
            >
              <input
                type="checkbox"
                checked={checked}
                disabled={!option.connected}
                onChange={() => {
                  const next = new Set(selected)
                  if (next.has(option.apiId)) next.delete(option.apiId)
                  else next.add(option.apiId)
                  onChange(next)
                }}
              />
              <span>
                <span className="name">{option.name}</span>
                <span className={`meta ${option.tone}`}>{option.meta}</span>
              </span>
            </label>
          )
        })}
      </div>
    </>
  )
}

export function SourcePicker({ options, selected, onChange }: SourcePickerProps) {
  return (
    <div className="sources-block">
      <div className="sources-head">
        <div className="field-label" style={{ margin: 0 }}>
          采集来源 <span className="optional">（统一 Provider API，均可选）</span>
        </div>
        <div className="sources-tools">
          <span className="source-count">已选 {selected.size} 个</span>
          <button
            className="btn ghost small"
            type="button"
            onClick={() => {
              const available = options.filter((option) => option.connected)
              const allSelected =
                available.length > 0 &&
                available.every((option) => selected.has(option.apiId))
              onChange(
                allSelected
                  ? new Set()
                  : new Set(available.map((option) => option.apiId)),
              )
            }}
          >
            全选可用来源
          </button>
        </div>
      </div>
      <SourceGroup
        title="Agent-Reach 适配器"
        options={options.filter((option) => option.group === 'reach')}
        selected={selected}
        onChange={onChange}
      />
      <SourceGroup
        title="其他适配器"
        options={options.filter((option) => option.group === 'other')}
        selected={selected}
        onChange={onChange}
      />
    </div>
  )
}
