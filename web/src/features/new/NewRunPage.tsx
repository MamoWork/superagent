import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { analyzeRun, createRun } from '../../api/endpoints'
import type { Run, RunCreatePayload } from '../../api/types'
import { SourcePicker } from '../../components/SourcePicker'
import { EmptyState, LoadingState } from '../../components/StateViews'
import { useToast } from '../../context/ToastContext'
import {
  mergeSources,
  providerName,
} from '../../data/sourceCatalog'
import { useAIStatus, useBackend } from '../../hooks/useBackend'
import { useRuns } from '../../hooks/useRuns'
import { getErrorMessage } from '../../lib/errors'
import { formatDateTime, formatElapsed } from '../../lib/format'
import { toTimeRangeDays } from '../../lib/timeRange'
import {
  ScheduleDialog,
  type ScheduleDefaults,
} from '../schedules/ScheduleDialog'

const EXAMPLES = [
  {
    label: '跨境选品机会',
    value:
      'Amazon 宠物饮水机细分，低评论高客单的机会在哪里？',
  },
  {
    label: '跨境卖家客服',
    value:
      '跨境卖家在客服和售后环节，有哪些重复劳动可以用工具解决？',
  },
  {
    label: '独立开发获客',
    value:
      '独立开发者获取前 100 个付费用户时，最常遇到的困难是什么？',
  },
  {
    label: '房产经纪视频字幕',
    value:
      '房产经纪人做短视频营销时，字幕和剪辑环节有什么痛点？',
  },
  {
    label: '本地生活 SaaS',
    value:
      '小型本地生活商家在预约、排班和客户跟进上有什么未被满足的需求？',
  },
]

type StepState = 'idle' | 'running' | 'done'
type Phase = 'idle' | 'running' | 'done' | 'error'

interface Step {
  label: string
  meta: string
  state: StepState
}

const STEP_LABELS = [
  '解析方向与关键词',
  '调用数据源适配器采集公开信号',
  '接收并整理 Provider 响应',
  '后端去重、相关性过滤',
  'AI 提炼痛点、付费信号与风险',
  '生成机会卡与来源链接',
]

function initialSteps(): Step[] {
  return STEP_LABELS.map((label) => ({
    label,
    meta: '等待中',
    state: 'idle',
  }))
}

export function NewRunPage() {
  const navigate = useNavigate()
  const { toast } = useToast()
  const { providers, packs, online, loading: backendLoading } = useBackend()
  const ai = useAIStatus()
  const recent = useRuns(3)

  const [direction, setDirection] = useState('')
  const [keywords, setKeywords] = useState('')
  const [domainPack, setDomainPack] = useState('general')
  const [range, setRange] = useState('90')
  const [limit, setLimit] = useState('20')
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [steps, setSteps] = useState<Step[]>(initialSteps)
  const [phase, setPhase] = useState<Phase>('idle')
  const [elapsed, setElapsed] = useState(0)
  const [startedAt, setStartedAt] = useState(0)
  const [runError, setRunError] = useState('')
  const [scheduleOpen, setScheduleOpen] = useState(false)
  const [scheduleDefaults, setScheduleDefaults] = useState<ScheduleDefaults>({})

  const initialised = useRef(false)

  const sources = useMemo(
    () => mergeSources(providers.data?.providers, online),
    [providers.data, online],
  )

  useEffect(() => {
    if (initialised.current || !online || !providers.data) return
    const defaults = mergeSources(providers.data.providers, true)
      .filter((option) => option.connected && option.defaultChecked)
      .map((option) => option.apiId)
    setSelected(new Set(defaults))
    initialised.current = true
  }, [online, providers.data])

  useEffect(() => {
    if (phase !== 'running') return
    const timer = window.setInterval(() => {
      setElapsed(Math.floor((Date.now() - startedAt) / 1000))
    }, 1_000)
    return () => window.clearInterval(timer)
  }, [phase, startedAt])

  const updateStep = (index: number, state: StepState, meta: string) => {
    setSteps((current) =>
      current.map((step, idx) => (idx === index ? { ...step, state, meta } : step)),
    )
  }

  const rangeDays = toTimeRangeDays(range)

  const start = async () => {
    if (!online) {
      toast('API 未连接，无法开始采集。', 'error')
      return
    }
    if (!direction.trim()) {
      toast('请先输入一个方向或关键词。', 'error')
      return
    }
    if (!selected.size) {
      toast('请选择至少一个可用的数据源。', 'error')
      return
    }

    setSteps(initialSteps())
    setRunError('')
    setElapsed(0)
    setStartedAt(Date.now())
    setPhase('running')
    updateStep(0, 'done', '已解析')
    updateStep(1, 'running', '采集中…')

    const payload: RunCreatePayload = {
      domain_pack: domainPack,
      direction: direction.trim(),
      keywords: keywords
        .split(',')
        .map((item) => item.trim())
        .filter(Boolean),
      provider_ids: Array.from(selected),
      limit_per_provider: Number(limit) || 20,
      time_range_days: rangeDays,
    }

    let run: Run
    try {
      run = await createRun(payload)
    } catch (error) {
      updateStep(1, 'done', '失败')
      setRunError(getErrorMessage(error))
      setPhase('error')
      toast(`采集失败：${getErrorMessage(error)}`, 'error')
      return
    }

    updateStep(1, 'done', `${run.signals.length} 条信号`)
    updateStep(2, 'done', run.provider_ids.length + ' 个来源')
    updateStep(3, 'done', '后端已去重')

    if (ai.data?.configured) {
      updateStep(4, 'running', 'AI 分析中…')
      try {
        const analysis = await analyzeRun(run.id)
        updateStep(
          4,
          'done',
          `${analysis.verdict} · ${analysis.score}`,
        )
      } catch (error) {
        updateStep(4, 'done', '分析失败')
        toast(
          `采集完成，但 AI 分析失败：${getErrorMessage(error)}`,
          'error',
        )
      }
    } else {
      updateStep(4, 'done', '未配置 AI')
    }

    updateStep(5, 'done', '已生成')
    setPhase('done')
    toast(`采集完成：${run.signals.length} 条公开信号`)
    navigate(`/results/${run.id}`)
  }

  const openSchedule = () => {
    setScheduleDefaults({
      direction: direction.trim(),
      keywords: keywords
        .split(',')
        .map((item) => item.trim())
        .filter(Boolean),
      domain_pack: domainPack,
      limit_per_provider: Number(limit) || 20,
      time_range_days: rangeDays,
      provider_ids: Array.from(selected),
    })
    setScheduleOpen(true)
  }

  const running = phase === 'running'
  const aiLabel = ai.data?.configured
    ? `${ai.data.model || '已配置'} · ${ai.data.provider || ''}`.trim()
    : '未配置（仅采集证据）'

  return (
    <section className="view active">
      <div className="hero">
        <div className="eyebrow">Business Opportunity Radar</div>
        <h1>
          告诉我一个方向，
          <br />
          我去把真实需求找回来。
        </h1>
        <p>
          输入关键词或一句描述，自动调用已接入的数据源（社区、网页、市场平台、RSS
          等）采集公开信号，用你配置的 AI
          提炼痛点、付费意愿与风险；确认机会后，进入验证、跟进与人工触达的获取闭环。每条结论都带可点击的源链接。
        </p>
      </div>

      <div className="panel">
        <div className="panel-head">
          <h2>新建采集</h2>
          <span className="badge ghost">只读采集公开内容</span>
        </div>

        <label className="field-label" htmlFor="direction">
          方向描述
        </label>
        <textarea
          id="direction"
          value={direction}
          onChange={(event) => setDirection(event.target.value)}
          placeholder="例：Amazon 宠物饮水机细分，低评论高客单的机会在哪里？"
          disabled={running}
        />
        <div className="chips">
          {EXAMPLES.map((example) => (
            <button
              className="chip"
              type="button"
              key={example.label}
              disabled={running}
              onClick={() => setDirection(example.value)}
            >
              {example.label}
            </button>
          ))}
        </div>

        <div className="form-grid">
          <div className="field">
            <label className="field-label" htmlFor="keywords">
              关键词 <span className="optional">（可选，逗号分隔）</span>
            </label>
            <input
              id="keywords"
              type="text"
              value={keywords}
              onChange={(event) => setKeywords(event.target.value)}
              placeholder="pet water fountain, stainless steel"
              disabled={running}
            />
          </div>
          <div className="field">
            <label className="field-label" htmlFor="domainPack">
              机会类型
            </label>
            <select
              id="domainPack"
              value={domainPack}
              onChange={(event) => setDomainPack(event.target.value)}
              disabled={running || !packs.data}
            >
              {(packs.data?.domain_packs ?? []).map((pack) => (
                <option value={pack.id} key={pack.id}>
                  {pack.id === 'general' ? '自动识别 / 通用' : pack.name}
                </option>
              ))}
              {!packs.data ? (
                <option value="general">
                  {backendLoading ? '加载领域包…' : 'API 未连接'}
                </option>
              ) : null}
            </select>
          </div>
          <div className="field">
            <label className="field-label" htmlFor="range">
              时间范围
            </label>
            <select
              id="range"
              value={range}
              onChange={(event) => setRange(event.target.value)}
              disabled={running}
            >
              <option value="30">最近 30 天</option>
              <option value="90">最近 90 天</option>
              <option value="365">最近 1 年</option>
              <option value="0">不限时间</option>
            </select>
          </div>
          <div className="field">
            <label className="field-label" htmlFor="limit">
              每个来源最多
            </label>
            <select
              id="limit"
              value={limit}
              onChange={(event) => setLimit(event.target.value)}
              disabled={running}
            >
              <option value="10">10 条</option>
              <option value="20">20 条</option>
              <option value="50">50 条</option>
            </select>
          </div>
          <div className="field">
            <label className="field-label" htmlFor="aiEngine">
              AI 引擎
            </label>
            <div className="select-row">
              <select id="aiEngine" value="" disabled>
                <option value="">
                  {ai.isLoading ? '检测中…' : aiLabel}
                </option>
              </select>
              <Link className="btn ghost small" to="/settings">
                配置
              </Link>
            </div>
          </div>
        </div>

        <SourcePicker
          options={sources}
          selected={selected}
          onChange={setSelected}
        />

        <div className="form-footer">
          <div className="hint">
            仅采集公开内容；结果用于调研，不自动发帖或联系用户。
          </div>
          <div className="form-actions">
            <button
              type="button"
              className="btn"
              onClick={openSchedule}
              disabled={running}
            >
              存为定时任务
            </button>
            <button
              type="button"
              className="btn primary large"
              onClick={start}
              disabled={running || !online}
              title={!online ? 'API 未连接' : undefined}
            >
              {running
                ? '采集中…'
                : ai.data?.configured
                  ? '开始采集与分析'
                  : '开始采集（仅证据）'}{' '}
              <span className="arrow">→</span>
            </button>
          </div>
        </div>
      </div>

      {phase !== 'idle' ? (
        <div className="panel progress-panel show">
          <div className="panel-head">
            <h2>{running ? '正在采集与分析' : '本次运行'}</h2>
            <span className="badge ghost">
              {running ? `已用 ${formatElapsed(elapsed)}` : '已结束'}
            </span>
          </div>
          <div className="steps">
            {steps.map((step, index) => (
              <div className={`step ${step.state}`} key={step.label}>
                <span className="step-dot">
                  {step.state === 'done' ? '✓' : index + 1}
                </span>
                <span>{step.label}</span>
                <span className="step-meta">{step.meta}</span>
              </div>
            ))}
          </div>
          <div
            className={`progress-bar${running ? ' indeterminate' : ''}${
              phase === 'error' ? ' failed' : ''
            }`}
          >
            <span />
          </div>
          <p className="hint" style={{ marginTop: 9 }}>
            进度不显示百分比：耗时取决于平台响应。若前端请求超时，后端可能仍在运行，请到「采集历史」查看结果。
          </p>
          {runError ? <p className="form-error">{runError}</p> : null}
        </div>
      ) : null}

      <div className="section-title">
        <h2>最近的采集</h2>
        <span className="muted">本机历史 · 点击查看</span>
      </div>

      {!online && !backendLoading ? (
        <EmptyState
          title="API 未连接"
          description="启动本地服务后，采集记录会显示在这里。"
        />
      ) : recent.isLoading ? (
        <LoadingState label="加载最近采集…" />
      ) : recent.data && recent.data.runs.length ? (
        <div className="recent-grid">
          {recent.data.runs.slice(0, 3).map((run) => (
            <Link
              className="recent-card"
              to={`/results/${run.id}`}
              key={run.id}
            >
              <div className="time">{formatDateTime(run.created_at)}</div>
              <div className="title">{run.direction}</div>
              <div className="meta">
                <span className="mini-badge">
                  {run.has_analysis ? '已分析' : '仅证据'}
                </span>
                <span>
                  {run.stats.signal_count ?? '—'} 条信号 ·{' '}
                  {run.provider_ids
                    .map((id) => providerName(providers.data?.providers, id))
                    .join(' · ')}
                </span>
              </div>
            </Link>
          ))}
        </div>
      ) : (
        <EmptyState
          title="暂无采集记录"
          description="发起一次采集，结果会自动出现在这里，并保存在本机 SQLite。"
        />
      )}

      <ScheduleDialog
        open={scheduleOpen}
        onClose={() => setScheduleOpen(false)}
        defaults={scheduleDefaults}
      />
    </section>
  )
}
