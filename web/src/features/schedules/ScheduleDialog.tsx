import { useMemo, useState } from 'react'
import { CRON_PRESETS } from '../../lib/cron'
import { mergeSources, withSelectedSources } from '../../data/sourceCatalog'
import { useAIStatus, useBackend } from '../../hooks/useBackend'
import {
  useCreateSchedule,
  useUpdateSchedule,
} from '../../hooks/useSchedules'
import { useToast } from '../../context/ToastContext'
import { getErrorMessage } from '../../lib/errors'
import type { Schedule } from '../../api/types'
import { Modal } from '../../components/Modal'

export interface ScheduleDefaults {
  direction?: string
  keywords?: string[]
  domain_pack?: string
  limit_per_provider?: number
  time_range_days?: number | null
  provider_ids?: string[]
}

interface ScheduleDialogProps {
  open: boolean
  onClose: () => void
  schedule?: Schedule | null
  defaults?: ScheduleDefaults
}

const DEFAULT_CRON = '0 9 * * *'

export function ScheduleDialog({
  open,
  onClose,
  schedule,
  defaults,
}: ScheduleDialogProps) {
  if (!open) return null
  return (
    <ScheduleDialogBody
      key={schedule?.id ?? 'new'}
      onClose={onClose}
      schedule={schedule}
      defaults={defaults}
    />
  )
}

function ScheduleDialogBody({
  onClose,
  schedule,
  defaults,
}: {
  onClose: () => void
  schedule?: Schedule | null
  defaults?: ScheduleDefaults
}) {
  const { providers, online } = useBackend()
  const ai = useAIStatus()
  const createSchedule = useCreateSchedule()
  const updateSchedule = useUpdateSchedule()
  const { toast } = useToast()

  const initialCron = schedule?.cron ?? DEFAULT_CRON
  const initialPreset = CRON_PRESETS.find((item) => item.value === initialCron)

  const [name, setName] = useState(schedule ? schedule.name : '')
  const [direction, setDirection] = useState(
    schedule?.direction ?? defaults?.direction ?? '',
  )
  const [keywords, setKeywords] = useState(
    (schedule?.keywords ?? defaults?.keywords ?? []).join(', '),
  )
  const [cronPreset, setCronPreset] = useState<string>(
    initialPreset ? initialPreset.value : 'custom',
  )
  const [customCron, setCustomCron] = useState(
    initialPreset ? '' : initialCron,
  )
  const [selected, setSelected] = useState<Set<string>>(
    () => new Set(schedule?.provider_ids ?? defaults?.provider_ids ?? []),
  )
  const [error, setError] = useState('')

  const options = useMemo(
    () => mergeSources(providers.data?.providers, online),
    [providers.data, online],
  )

  const visibleOptions = useMemo(
    () => withSelectedSources(options, selected),
    [options, selected],
  )

  const domainPack = schedule?.domain_pack ?? defaults?.domain_pack ?? 'general'
  const limit =
    schedule?.limit_per_provider ?? defaults?.limit_per_provider ?? 20
  const range =
    schedule?.time_range_days !== undefined
      ? schedule.time_range_days
      : (defaults?.time_range_days ?? null)

  const pending = createSchedule.isPending || updateSchedule.isPending
  const editing = Boolean(schedule)

  const submit = () => {
    const trimmedName = name.trim()
    const trimmedDirection = direction.trim()
    const cron = cronPreset === 'custom' ? customCron.trim() : cronPreset
    if (!trimmedName || !trimmedDirection) {
      setError('请填写任务名称和方向描述。')
      return
    }
    if (!cron) {
      setError('请填写 cron 表达式。')
      return
    }
    if (!selected.size) {
      setError('请至少选择一个已接入来源。')
      return
    }
    if (!online) {
      setError('API 未连接，无法保存定时任务。')
      return
    }
    const payload = {
      name: trimmedName,
      direction: trimmedDirection,
      keywords: keywords
        .split(',')
        .map((item) => item.trim())
        .filter(Boolean),
      provider_ids: Array.from(selected),
      domain_pack: domainPack,
      limit_per_provider: limit,
      time_range_days: range,
      cron,
    }
    const done = () => {
      toast(editing ? '定时任务已更新' : `定时任务已保存：${trimmedName}`)
      onClose()
    }
    if (schedule) {
      updateSchedule.mutate(
        { id: schedule.id, payload },
        {
          onSuccess: done,
          onError: (err) =>
            setError(`保存失败：${getErrorMessage(err)}`),
        },
      )
    } else {
      createSchedule.mutate(payload, {
        onSuccess: done,
        onError: (err) => setError(`保存失败：${getErrorMessage(err)}`),
      })
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title={editing ? '编辑定时任务' : '新建定时任务'}
      badge={<span className="badge ghost">本地调度</span>}
      maxWidth={720}
      footer={
        <>
          <button type="button" className="btn" onClick={onClose}>
            取消
          </button>
          <button
            type="button"
            className="btn primary"
            onClick={submit}
            disabled={pending || !online}
          >
            {pending ? '保存中…' : '保存任务'}
          </button>
        </>
      }
    >
      <div className="field" style={{ marginTop: 12 }}>
        <label className="field-label" htmlFor="scheduleName">
          任务名称
        </label>
        <input
          id="scheduleName"
          type="text"
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="例：房产字幕 · 每日扫描"
        />
      </div>
      <div className="field" style={{ marginTop: 10 }}>
        <label className="field-label" htmlFor="scheduleDirection">
          方向描述
        </label>
        <textarea
          id="scheduleDirection"
          style={{ minHeight: 64 }}
          value={direction}
          onChange={(event) => setDirection(event.target.value)}
          placeholder="输入要持续追踪的方向或问题"
        />
      </div>
      <div className="modal-grid" style={{ marginTop: 10 }}>
        <div className="field">
          <label className="field-label" htmlFor="scheduleKeywords">
            关键词 <span className="optional">（可选）</span>
          </label>
          <input
            id="scheduleKeywords"
            type="text"
            value={keywords}
            onChange={(event) => setKeywords(event.target.value)}
            placeholder="caption, realtor"
          />
        </div>
        <div className="field">
          <label className="field-label" htmlFor="scheduleFreq">
            频率
          </label>
          <select
            id="scheduleFreq"
            value={cronPreset}
            onChange={(event) => setCronPreset(event.target.value)}
          >
            {CRON_PRESETS.map((preset) => (
              <option value={preset.value} key={preset.value}>
                {preset.label}
              </option>
            ))}
            <option value="custom">自定义 cron…</option>
          </select>
          {cronPreset === 'custom' ? (
            <input
              type="text"
              value={customCron}
              onChange={(event) => setCustomCron(event.target.value)}
              placeholder="5 段 cron，例如 0 9 * * *"
              style={{ marginTop: 8 }}
            />
          ) : null}
        </div>
      </div>

      <div className="field" style={{ marginTop: 12 }}>
        <label className="field-label">
          采集来源 <span className="optional">（只列出当前可用的适配器）</span>
        </label>
        <div className="schedule-sources">
          {visibleOptions.map((option) => (
            <label key={option.id} title={option.meta}>
              <input
                type="checkbox"
                checked={selected.has(option.apiId)}
                disabled={!option.connected}
                onChange={() => {
                  const next = new Set(selected)
                  if (next.has(option.apiId)) next.delete(option.apiId)
                  else next.add(option.apiId)
                  setSelected(next)
                }}
              />
              {option.name}
            </label>
          ))}
        </div>
      </div>

      <p className="hint" style={{ marginTop: 10 }}>
        领域包：{domainPack} · 每个来源 {limit} 条 · 时间范围：
        {range ? `最近 ${range} 天` : '不限'} · AI：
        {ai.data?.configured ? ai.data.model || '已配置' : '未配置（仅采集）'}
      </p>
      <p className="hint" style={{ marginTop: 6 }}>
        任务保存在本机 SQLite；API 运行时按 cron 触发。领域包、条数与时间范围沿用
        {editing ? '任务原配置' : '「新建采集」当前设置'}，只在编辑时保留，不在本弹窗修改。
        只读采集，不会自动发帖或私信。
      </p>
      {!online ? (
        <p className="form-error">API 未连接，无法保存定时任务。</p>
      ) : null}
      {error ? <p className="form-error">{error}</p> : null}
    </Modal>
  )
}
