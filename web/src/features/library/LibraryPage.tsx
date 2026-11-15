import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import type { SavedOpportunity } from '../../api/types'
import { VerdictBadge } from '../../components/Badge'
import { ConfirmDialog } from '../../components/ConfirmDialog'
import { OpportunityDetailDialog } from '../../components/OpportunityDetailDialog'
import { ScoreRing } from '../../components/ScoreRing'
import { SourceLink } from '../../components/SourceLink'
import { EmptyState, ErrorState, LoadingState } from '../../components/StateViews'
import { useToast } from '../../context/ToastContext'
import { useDeleteOpportunity, useLibrary } from '../../hooks/useLibrary'
import { downloadJson } from '../../lib/download'
import { getErrorMessage } from '../../lib/errors'
import { formatDateTime } from '../../lib/format'
import { stageLabel } from '../../lib/status'

function savedCitations(item: SavedOpportunity) {
  return item.citations.map((citation) => ({
    title: citation.source_url || '引用来源',
    url: citation.source_url,
    meta: `AI 引用${citation.signal_id ? ` · ${citation.signal_id}` : ''}`,
    quote: citation.quote,
  }))
}

export function LibraryPage() {
  const { toast } = useToast()
  const library = useLibrary()
  const remove = useDeleteOpportunity()
  const [detail, setDetail] = useState<SavedOpportunity | null>(null)
  const [deleting, setDeleting] = useState<SavedOpportunity | null>(null)

  const items = library.data?.opportunities ?? []
  const detailData = useMemo(
    () =>
      detail
        ? {
            title: detail.title,
            score: detail.score,
            verdict: detail.verdict,
            thesis: detail.thesis,
            target_customer: detail.target_customer,
            willingness_to_pay: detail.willingness_to_pay,
            risks: detail.risks,
            next_actions: detail.next_actions,
            dimension_scores: detail.dimension_scores,
            citations: savedCitations(detail),
          }
        : null,
    [detail],
  )

  const exportLibrary = () => {
    downloadJson('opportunity-library.json', { opportunities: items })
    toast('已导出机会库')
  }

  return (
    <section className="view active">
      <div className="view-head">
        <div>
          <div className="eyebrow">Saved Opportunities</div>
          <h1>机会库</h1>
          <div className="muted">
            已收藏的机会保留来源链接与 AI 分析快照，方便后续跟进验证。
          </div>
        </div>
        <div className="head-actions">
          <button
            className="btn"
            type="button"
            onClick={exportLibrary}
            disabled={!items.length}
          >
            导出机会库
          </button>
        </div>
      </div>

      {library.isLoading ? (
        <LoadingState label="加载机会库…" />
      ) : library.isError ? (
        <ErrorState
          title="无法读取机会库"
          message={getErrorMessage(library.error)}
          onRetry={() => void library.refetch()}
        />
      ) : items.length ? (
        <div className="opp-list">
          {items.map((item) => (
            <article className="opp-card" key={item.run_id}>
              <ScoreRing score={item.score} />
              <div className="opp-main">
                <div className="opp-top">
                  <div>
                    <VerdictBadge verdict={item.verdict} />
                    <h3>{item.title}</h3>
                  </div>
                  <div className="opp-actions">
                    <button
                      className="btn ghost small"
                      type="button"
                      onClick={() => setDetail(item)}
                    >
                      查看详情
                    </button>
                  </div>
                </div>
                <p className="opp-pain">{item.thesis}</p>
                <div className="opp-meta">
                  <div className="meta-item">
                    <b>目标用户：</b>
                    {item.target_customer || '—'}
                  </div>
                  <div className="meta-item">
                    <b>付费信号：</b>
                    {item.willingness_to_pay || '—'}
                  </div>
                </div>
                {item.citations.length ? (
                  <div className="evidence">
                    <div className="evidence-label">核心证据</div>
                    {savedCitations(item)
                      .slice(0, 2)
                      .map((source, index) => (
                        <SourceLink
                          source={source}
                          key={`${source.url}-${index}`}
                        />
                      ))}
                  </div>
                ) : null}
                <div className="tag-row">
                  <span className="tag">阶段：{stageLabel(item.stage)}</span>
                  <span className="tag">
                    保存于 {formatDateTime(item.created_at)}
                  </span>
                  {item.notes ? (
                    <span className="tag">备注：{item.notes}</span>
                  ) : null}
                </div>
                <div className="opp-footer">
                  <Link className="btn ghost small" to={`/results/${item.run_id}`}>
                    打开原始 Run
                  </Link>
                  <Link className="btn ghost small" to="/pipeline">
                    进入闭环
                  </Link>
                  <button
                    className="btn ghost small"
                    type="button"
                    onClick={() => setDeleting(item)}
                  >
                    删除
                  </button>
                </div>
              </div>
            </article>
          ))}
        </div>
      ) : (
        <EmptyState
          title="机会库还是空的"
          description="在机会分析页点击「收藏到机会库」，这里会保存分析快照与来源链接。"
          action={
            <Link className="btn primary" to="/results">
              去机会分析
            </Link>
          }
        />
      )}

      <OpportunityDetailDialog
        open={Boolean(detail)}
        onClose={() => setDetail(null)}
        data={detailData}
        footer={
          detail ? (
            <>
              <button className="btn" type="button" onClick={() => setDetail(null)}>
                关闭
              </button>
              <Link className="btn" to={`/results/${detail.run_id}`}>
                打开原始 Run
              </Link>
              <Link className="btn primary" to="/pipeline">
                进入获取闭环 →
              </Link>
            </>
          ) : null
        }
      />

      <ConfirmDialog
        open={Boolean(deleting)}
        title="删除机会"
        message={`确定从机会库删除「${deleting?.title || ''}」？原始 Run 与采集记录会保留。`}
        confirmLabel="删除"
        pending={remove.isPending}
        onClose={() => setDeleting(null)}
        onConfirm={() => {
          if (!deleting) return
          remove.mutate(deleting.run_id, {
            onSuccess: () => {
              toast('已从机会库删除')
              setDeleting(null)
            },
            onError: (error) =>
              toast(`删除失败：${getErrorMessage(error)}`, 'error'),
          })
        }}
      />
    </section>
  )
}
