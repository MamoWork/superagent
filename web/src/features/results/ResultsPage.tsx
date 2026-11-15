import { useMemo, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { analyzeRun } from '../../api/endpoints'
import { queryKeys } from '../../api/queryKeys'
import type {
  Citation,
  OpportunityAnalysis,
  ProviderInfo,
  Signal,
} from '../../api/types'
import { VerdictBadge } from '../../components/Badge'
import { OpportunityDetailDialog } from '../../components/OpportunityDetailDialog'
import { ProviderErrors } from '../../components/ProviderErrors'
import { ScoreRing } from '../../components/ScoreRing'
import { SourceLink } from '../../components/SourceLink'
import {
  EmptyState,
  ErrorState,
  LoadingState,
} from '../../components/StateViews'
import { useToast } from '../../context/ToastContext'
import { providerName } from '../../data/sourceCatalog'
import { useAIStatus, useProviders } from '../../hooks/useBackend'
import { useLibrary, useSaveOpportunity } from '../../hooks/useLibrary'
import { useAnalysis, useRun } from '../../hooks/useRuns'
import { downloadJson } from '../../lib/download'
import { getErrorMessage } from '../../lib/errors'
import { formatDateTime } from '../../lib/format'
import { runStatusMeta, verdictMeta } from '../../lib/status'
import type { SourceLinkData } from '../../components/SourceLink'

function resolveCitations(
  citations: Citation[],
  signals: Signal[],
  providers: ProviderInfo[] | undefined,
): SourceLinkData[] {
  return citations.map((citation) => {
    const signal = signals.find((item) => item.id === citation.signal_id)
    if (!signal) {
      return {
        title: citation.source_url || '引用来源',
        url: citation.source_url,
        meta: 'AI 引用',
        quote: citation.quote,
      }
    }
    const meta = [
      providerName(providers, signal.provider_id),
      signal.author_public,
      signal.published_at?.slice(0, 10),
    ]
      .filter(Boolean)
      .join(' · ')
    return {
      title: signal.title || signal.source_url,
      url: signal.source_url,
      meta,
      quote: signal.quote || citation.quote,
    }
  })
}

function signalSource(
  signal: Signal,
  providers: ProviderInfo[] | undefined,
): SourceLinkData {
  return {
    title: signal.title || signal.source_url,
    url: signal.source_url,
    meta: [
      providerName(providers, signal.provider_id),
      signal.author_public,
      signal.published_at?.slice(0, 10),
    ]
      .filter(Boolean)
      .join(' · '),
    quote: signal.quote,
  }
}

const FILTERS = [
  { id: 'all', label: '全部' },
  { id: 'high', label: '高机会' },
  { id: 'verify', label: '待验证' },
  { id: 'red', label: '红海' },
] as const

type FilterId = (typeof FILTERS)[number]['id']

function matchesFilter(analysis: OpportunityAnalysis, filter: FilterId): boolean {
  if (filter === 'all') return true
  if (filter === 'high') return analysis.score >= 80
  if (filter === 'verify') return analysis.verdict === 'verify'
  return analysis.verdict === 'drop'
}

export function ResultsPage() {
  const { runId } = useParams<{ runId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const [params, setParams] = useSearchParams()
  const filter = (params.get('filter') || 'all') as FilterId
  const [detailOpen, setDetailOpen] = useState(false)

  const runQuery = useRun(runId)
  const run = runQuery.data
  const analysisQuery = useAnalysis(runId, Boolean(run?.has_analysis))
  const analysis = analysisQuery.data
  const ai = useAIStatus()
  const providersQuery = useProviders()
  const providers = providersQuery.data?.providers
  const library = useLibrary()
  const saveMutation = useSaveOpportunity()

  const analyzeMutation = useMutation({
    mutationFn: () => analyzeRun(runId as string),
    onSuccess: () => {
      if (runId) {
        void queryClient.invalidateQueries({ queryKey: queryKeys.run(runId) })
        void queryClient.invalidateQueries({
          queryKey: queryKeys.analysis(runId),
        })
      }
      toast('AI 分析已完成')
    },
    onError: (error) => toast(`分析失败：${getErrorMessage(error)}`, 'error'),
  })

  const saved = library.data?.opportunities.find(
    (item) => item.run_id === runId,
  )

  const sources = useMemo(
    () =>
      resolveCitations(
        analysis?.citations ?? [],
        run?.signals ?? [],
        providers,
      ),
    [analysis, run, providers],
  )

  if (runQuery.isLoading) {
    return (
      <section className="view active">
        <LoadingState label="加载 Run…" />
      </section>
    )
  }

  if (runQuery.isError || !run) {
    return (
      <section className="view active">
        <ErrorState
          title="无法加载 Run"
          message={getErrorMessage(runQuery.error)}
          onRetry={() => void runQuery.refetch()}
        />
        <div className="empty-action">
          <Link className="btn" to="/history">
            返回采集历史
          </Link>
        </div>
      </section>
    )
  }

  const status = runStatusMeta(run.status)
  const signalCount = run.stats.signal_count ?? run.signals.length
  const verdict = analysis ? verdictMeta(analysis.verdict) : null

  const visibleFilters: FilterId[] = analysis
    ? FILTERS.filter((item) => item.id === 'all' || matchesFilter(analysis, item.id)).map(
        (item) => item.id,
      )
    : ['all']

  const activeFilter = visibleFilters.includes(filter) ? filter : 'all'
  const showOpportunity =
    analysis !== undefined && matchesFilter(analysis, activeFilter)

  const detailData = analysis
    ? {
        title: analysis.one_liner || run.direction,
        score: analysis.score,
        verdict: analysis.verdict,
        thesis: analysis.thesis,
        target_customer: analysis.target_customer,
        willingness_to_pay: analysis.willingness_to_pay,
        risks: analysis.risks,
        next_actions: analysis.next_actions,
        dimension_scores: analysis.dimension_scores,
        missing_information: analysis.missing_information,
        citations: resolveCitations(
          analysis.citations,
          run.signals,
          providers,
        ),
      }
    : null

  const saveOnly = async () => {
    try {
      await saveMutation.mutateAsync({ runId: run.id })
      toast('已加入机会库')
    } catch (error) {
      toast(`保存失败：${getErrorMessage(error)}`, 'error')
    }
  }

  const acquire = async () => {
    if (!saved) {
      try {
        await saveMutation.mutateAsync({ runId: run.id })
      } catch (error) {
        toast(`保存失败：${getErrorMessage(error)}`, 'error')
        return
      }
    }
    toast('已加入机会库，进入获取闭环')
    navigate('/pipeline')
  }

  const exportRun = () => {
    downloadJson(`run-${run.id}.json`, {
      run,
      analysis: analysis ?? null,
    })
    toast(`已导出 run-${run.id}.json`)
  }

  return (
    <section className="view active">
      <div className="view-head">
        <div>
          <div className="eyebrow">Run {run.id}</div>
          <h1>{run.direction} · 分析</h1>
          <div className="muted">
            {signalCount} 条信号 · 来源{' '}
            {run.provider_ids
              .map((id) => providerName(providers, id))
              .join(' / ') || '—'}{' '}
            · 状态 {status.label} · {formatDateTime(run.created_at)}
          </div>
        </div>
        <div className="head-actions">
          <button className="btn" type="button" onClick={exportRun}>
            导出 JSON
          </button>
          <Link className="btn primary" to="/">
            新建采集
          </Link>
        </div>
      </div>

      <div className="run-stats">
        <div className="stat">
          <div className="label">公开信号</div>
          <div className="value">{signalCount}</div>
        </div>
        <div className="stat">
          <div className="label">来源数</div>
          <div className="value">{run.provider_ids.length}</div>
        </div>
        <div className="stat">
          <div className="label">AI 判断</div>
          <div className="value" style={{ fontSize: 20, paddingTop: 5 }}>
            {verdict ? verdict.label : '未分析'}
          </div>
        </div>
        <div className="stat">
          <div className="label">机会评分</div>
          <div
            className="value"
            style={{ color: analysis ? undefined : 'var(--muted-2)' }}
          >
            {analysis ? analysis.score : '—'}
          </div>
        </div>
      </div>

      {run.stats.provider_errors ? (
        <ProviderErrors
          errors={run.stats.provider_errors}
          providers={providers}
        />
      ) : null}

      {analysis ? (
        <>
          <div className="toolbar">
            <div className="tabs">
              {FILTERS.filter((item) => visibleFilters.includes(item.id)).map(
                (item) => (
                  <button
                    key={item.id}
                    className={`tab${activeFilter === item.id ? ' active' : ''}`}
                    type="button"
                    onClick={() => {
                      if (item.id === 'all') setParams({})
                      else setParams({ filter: item.id })
                    }}
                  >
                    {item.label}{' '}
                    {matchesFilter(analysis, item.id) ? 1 : 0}
                  </button>
                ),
              )}
            </div>
            <div className="hint">每条机会均附原始链接，可直接打开核对</div>
          </div>

          {showOpportunity ? (
            <div className="opp-list">
              <article className="opp-card" data-filter={verdict?.tone}>
                <ScoreRing score={analysis.score} />
                <div className="opp-main">
                  <div className="opp-top">
                    <div>
                      <VerdictBadge verdict={analysis.verdict} />
                      <h3>{analysis.one_liner || run.direction}</h3>
                    </div>
                    <div className="opp-actions">
                      <button
                        className="btn small"
                        type="button"
                        onClick={acquire}
                        disabled={saveMutation.isPending}
                      >
                        进入闭环
                      </button>
                      <button
                        className="btn ghost small"
                        type="button"
                        onClick={() => setDetailOpen(true)}
                      >
                        查看详情
                      </button>
                    </div>
                  </div>
                  <p className="opp-pain">{analysis.thesis}</p>
                  <div className="opp-meta">
                    <div className="meta-item">
                      <b>目标用户：</b>
                      {analysis.target_customer || '—'}
                    </div>
                    <div className="meta-item">
                      <b>付费信号：</b>
                      {analysis.willingness_to_pay || '—'}
                    </div>
                  </div>
                  <div className="evidence">
                    <div className="evidence-label">
                      核心证据 · 点击跳转原文
                    </div>
                    {sources.slice(0, 2).map((source, index) => (
                      <SourceLink
                        source={source}
                        key={`${source.url}-${index}`}
                      />
                    ))}
                  </div>
                  <div className="tag-row">
                    {analysis.dimension_scores.slice(0, 4).map((dimension) => (
                      <span className="tag" key={dimension.dimension_id}>
                        {dimension.name} {dimension.score}/10
                      </span>
                    ))}
                    {analysis.risks[0] ? (
                      <span className="tag risk">
                        风险：{analysis.risks[0]}
                      </span>
                    ) : null}
                  </div>
                  <div className="opp-footer">
                    <button
                      className="btn ghost small"
                      type="button"
                      onClick={saveOnly}
                      disabled={Boolean(saved) || saveMutation.isPending}
                    >
                      {saved ? '已收藏到机会库' : '☆ 收藏到机会库'}
                    </button>
                    {saved ? (
                      <Link className="btn ghost small" to="/pipeline">
                        查看闭环
                      </Link>
                    ) : null}
                    <span className="hint">
                      分析模型：{analysis.model} ·{' '}
                      {formatDateTime(analysis.created_at)}
                    </span>
                  </div>
                </div>
              </article>
            </div>
          ) : (
            <EmptyState
              title="当前筛选没有机会"
              description="切换到「全部」查看本次分析结果。"
              action={
                <button
                  className="btn"
                  type="button"
                  onClick={() => setParams({})}
                >
                  查看全部
                </button>
              }
            />
          )}
        </>
      ) : analysisQuery.isLoading ? (
        <LoadingState label="加载 AI 分析…" />
      ) : (
        <div className="opp-list">
          <article className="opp-card">
            <div className="opp-main">
              <div className="opp-top">
                <div>
                  <span className="badge verify">仅证据</span>
                  <h3>{run.direction}</h3>
                </div>
                <div className="opp-actions">
                  {ai.data?.configured && !analysisQuery.isFetching ? (
                    <button
                      className="btn primary small"
                      type="button"
                      onClick={() => analyzeMutation.mutate()}
                      disabled={analyzeMutation.isPending}
                    >
                      {analyzeMutation.isPending ? '分析中…' : '运行 AI 分析'}
                    </button>
                  ) : null}
                </div>
              </div>
              <p className="opp-pain">
                {analysisQuery.isError
                  ? `无法读取 AI 分析：${getErrorMessage(analysisQuery.error)}。以下是本次采集到的公开信号，请人工核对。`
                  : ai.data?.configured
                    ? '本次 Run 还没有 AI 分析。你可以现在运行分析，或先核对下面的公开信号。'
                    : '后端未配置 AI 引擎。以下是本次采集到的公开信号，请人工核对后再判断。'}
              </p>
              <div className="evidence">
                <div className="evidence-label">
                  公开信号 · {run.signals.length} 条 · 点击跳转原文
                </div>
                {run.signals.length ? (
                  run.signals.map((signal) => (
                    <SourceLink
                      source={signalSource(signal, providers)}
                      key={signal.id}
                    />
                  ))
                ) : (
                  <p className="hint">
                    本次没有采集到信号。请检查数据源状态、查询词或平台限流；本工具不会换账号反复请求。
                  </p>
                )}
              </div>
              {!ai.data?.configured ? (
                <p className="hint" style={{ marginTop: 10 }}>
                  配置 AI：在后端启动环境中设置{' '}
                  <code>OPPORTUNITY_AI_MODEL</code> 与{' '}
                  <code>OPPORTUNITY_AI_API_KEY</code>，详见设置页。
                </p>
              ) : null}
            </div>
          </article>
        </div>
      )}

      <OpportunityDetailDialog
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
        data={detailData}
        footer={
          <>
            <button
              className="btn"
              type="button"
              onClick={() => setDetailOpen(false)}
            >
              关闭
            </button>
            <button
              className="btn"
              type="button"
              onClick={saveOnly}
              disabled={Boolean(saved) || saveMutation.isPending}
            >
              {saved ? '已加入机会库' : '加入机会库'}
            </button>
            <button className="btn primary" type="button" onClick={acquire}>
              进入获取闭环 →
            </button>
          </>
        }
      />
    </section>
  )
}
