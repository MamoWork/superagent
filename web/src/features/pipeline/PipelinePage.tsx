import { Fragment, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import type { SavedOpportunity, SavedStage } from '../../api/types'
import { VerdictBadge } from '../../components/Badge'
import { Modal } from '../../components/Modal'
import { OpportunityDetailDialog } from '../../components/OpportunityDetailDialog'
import { EmptyState, ErrorState, LoadingState } from '../../components/StateViews'
import { useToast } from '../../context/ToastContext'
import {
  useLibrary,
  useUpdateOpportunity,
} from '../../hooks/useLibrary'
import { downloadCsv } from '../../lib/csv'
import { getErrorMessage } from '../../lib/errors'
import { formatDateTime } from '../../lib/format'
import { STAGES, stageLabel } from '../../lib/status'
import { OutreachDialog } from './OutreachDialog'

function savedCitations(item: SavedOpportunity) {
  return item.citations.map((citation) => ({
    title: citation.source_url || '引用来源',
    url: citation.source_url,
    meta: `AI 引用${citation.signal_id ? ` · ${citation.signal_id}` : ''}`,
    quote: citation.quote,
  }))
}

export function PipelinePage() {
  const { toast } = useToast()
  const library = useLibrary()
  const update = useUpdateOpportunity()

  const [detail, setDetail] = useState<SavedOpportunity | null>(null)
  const [outreach, setOutreach] = useState<SavedOpportunity | null>(null)
  const [notesItem, setNotesItem] = useState<SavedOpportunity | null>(null)
  const [notesText, setNotesText] = useState('')

  const items = useMemo(
    () => library.data?.opportunities ?? [],
    [library.data],
  )
  const byStage = useMemo(() => {
    const map = new Map<SavedStage, SavedOpportunity[]>()
    for (const stage of STAGES) map.set(stage.id, [])
    for (const item of items) {
      map.get(item.stage)?.push(item)
    }
    return map
  }, [items])

  const funnel = [
    { label: '发现机会', value: items.length },
    { label: '验证中', value: byStage.get('validating')?.length ?? 0 },
    { label: '已触达', value: byStage.get('contacted')?.length ?? 0 },
    { label: '已回复', value: byStage.get('replied')?.length ?? 0 },
    { label: '已转化', value: byStage.get('won')?.length ?? 0 },
  ]

  const detailData = detail
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
    : null

  const changeStage = (item: SavedOpportunity, stage: SavedStage) => {
    update.mutate(
      { runId: item.run_id, payload: { stage } },
      {
        onSuccess: () => toast(`阶段已更新：${stageLabel(stage)}`),
        onError: (error) =>
          toast(`更新失败：${getErrorMessage(error)}`, 'error'),
      },
    )
  }

  const exportCsv = () => {
    downloadCsv(`opportunities-${new Date().toISOString().slice(0, 10)}.csv`, [
      ['标题', '分数', '判断', '阶段', '方向', '来源', '保存时间', '备注'],
      ...items.map((item) => [
        item.title,
        item.score,
        item.verdict,
        stageLabel(item.stage),
        item.direction,
        item.citations.map((citation) => citation.source_url).join(' | '),
        formatDateTime(item.created_at),
        item.notes,
      ]),
    ])
    toast('已导出机会 CSV')
  }

  return (
    <section className="view active">
      <div className="view-head">
        <div>
          <div className="eyebrow">Discovery → Validation → Acquisition</div>
          <h1>获取闭环</h1>
          <div className="muted">
            从公开信号到验证与人工触达，数据全部来自本机机会库；每条机会都保留来源链接。
          </div>
        </div>
        <div className="head-actions">
          <button
            className="btn"
            type="button"
            onClick={exportCsv}
            disabled={!items.length}
          >
            导出机会 CSV
          </button>
          <Link className="btn primary" to="/results">
            回到机会分析
          </Link>
        </div>
      </div>

      <div className="funnel">
        {funnel.map((step, index) => (
          <Fragment key={step.label}>
            <div className={`funnel-step${step.label === '已转化' ? ' won' : ''}`}>
              <div className="fv">{step.value}</div>
              <div className="fl">{step.label}</div>
            </div>
            {index < funnel.length - 1 ? (
              <div className="funnel-arrow">→</div>
            ) : null}
          </Fragment>
        ))}
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
        <div className="pipeline-board">
          {STAGES.map((stage) => {
            const stageItems = byStage.get(stage.id) ?? []
            return (
              <div className="pipe-col" key={stage.id}>
                <div className="pipe-head">
                  <span>{stage.label}</span>
                  <span className="count">{stageItems.length}</span>
                </div>
                {stageItems.map((item) => {
                  const source = item.citations[0]
                  return (
                    <article
                      className={`pipe-card${item.verdict === 'build' ? ' highlight' : ''}`}
                      key={item.run_id}
                    >
                      <div className="pipe-top">
                        <VerdictBadge verdict={item.verdict} />
                        <span className="pipe-score">{item.score}</span>
                      </div>
                      <h4>{item.title}</h4>
                      <p>{item.thesis}</p>
                      {source?.source_url ? (
                        <a
                          className="pipe-link"
                          href={source.source_url}
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          查看源链接 ↗
                        </a>
                      ) : null}
                      <div className="pipe-stage">
                        <label htmlFor={`stage-${item.run_id}`}>阶段</label>
                        <select
                          id={`stage-${item.run_id}`}
                          value={item.stage}
                          onChange={(event) =>
                            changeStage(item, event.target.value as SavedStage)
                          }
                          disabled={update.isPending}
                        >
                          {STAGES.map((option) => (
                            <option value={option.id} key={option.id}>
                              {option.label}
                            </option>
                          ))}
                        </select>
                      </div>
                      {item.notes ? (
                        <div className="next-action">{item.notes}</div>
                      ) : null}
                      <div className="pipe-actions">
                        <button
                          className="btn ghost small"
                          type="button"
                          onClick={() => setDetail(item)}
                        >
                          详情
                        </button>
                        <button
                          className="btn ghost small"
                          type="button"
                          onClick={() => {
                            setNotesItem(item)
                            setNotesText(item.notes)
                          }}
                        >
                          备注
                        </button>
                        <button
                          className="btn ghost small"
                          type="button"
                          onClick={() => setOutreach(item)}
                        >
                          触达模板
                        </button>
                        <Link
                          className="btn ghost small"
                          to={`/results/${item.run_id}`}
                        >
                          原 Run
                        </Link>
                      </div>
                    </article>
                  )
                })}
                {!stageItems.length ? (
                  <p className="pipe-empty">暂无机会</p>
                ) : null}
              </div>
            )
          })}
        </div>
      ) : (
        <EmptyState
          title="闭环里还没有机会"
          description="先在机会分析页收藏一条机会，它会出现在「待验证」列。"
          action={
            <Link className="btn primary" to="/results">
              去选择机会
            </Link>
          }
        />
      )}

      <div className="panel" style={{ marginTop: 16 }}>
        <div className="panel-head">
          <h2>验证方法示例</h2>
          <span className="badge ghost">只讲方法，不预填结果</span>
        </div>
        <div className="table-wrap" style={{ boxShadow: 'none', borderRadius: 10 }}>
          <table>
            <thead>
              <tr>
                <th>验证方法</th>
                <th>怎么做</th>
                <th>看什么信号</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>用户访谈</td>
                <td>找 5–10 位目标用户，问当前流程、耗时与替代方案。</td>
                <td>问题是否反复出现、是否已在花钱或花时间解决。</td>
              </tr>
              <tr>
                <td>预售 / 落地页</td>
                <td>用一页说明与可点击的预订按钮测试真实意愿。</td>
                <td>留言、预订或愿意留下联系方式的比例。</td>
              </tr>
              <tr>
                <td>手动交付</td>
                <td>先人工完成服务，验证结果是否被反复使用。</td>
                <td>复购、转介绍与愿意付费的具体场景。</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div className="panel compliance">
        <div className="panel-head">
          <h2>获取与合规边界</h2>
          <span className="badge ghost">只读采集 · 人工触达</span>
        </div>
        <p>
          本工具只读取公开内容，<b>不自动发帖、评论或私信</b>。触达模板由你本人复制并手动发送；线索来源链接会一直保留，方便核实与复盘。请遵守 Reddit
          等平台的频率与反垃圾规则。
        </p>
      </div>

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
              <button
                className="btn primary"
                type="button"
                onClick={() => {
                  setDetail(null)
                  setOutreach(detail)
                }}
              >
                生成触达模板 →
              </button>
            </>
          ) : null
        }
      />

      <Modal
        open={Boolean(notesItem)}
        onClose={() => setNotesItem(null)}
        title={`备注 · ${notesItem?.title || ''}`}
        badge={<span className="badge ghost">仅保存在本机</span>}
        maxWidth={560}
        footer={
          <>
            <button className="btn" type="button" onClick={() => setNotesItem(null)}>
              取消
            </button>
            <button
              className="btn primary"
              type="button"
              disabled={update.isPending}
              onClick={() => {
                if (!notesItem) return
                update.mutate(
                  {
                    runId: notesItem.run_id,
                    payload: { notes: notesText },
                  },
                  {
                    onSuccess: () => {
                      toast('备注已保存')
                      setNotesItem(null)
                    },
                    onError: (error) =>
                      toast(`保存失败：${getErrorMessage(error)}`, 'error'),
                  },
                )
              }}
            >
              保存备注
            </button>
          </>
        }
      >
        <div className="field" style={{ marginTop: 12 }}>
          <label className="field-label" htmlFor="oppNotes">
            跟进备注
          </label>
          <textarea
            id="oppNotes"
            style={{ minHeight: 140 }}
            value={notesText}
            onChange={(event) => setNotesText(event.target.value)}
            placeholder="例：已访谈 2 位用户；下一步发送模板；等待回复…"
            maxLength={5000}
          />
        </div>
      </Modal>

      <OutreachDialog
        open={Boolean(outreach)}
        onClose={() => setOutreach(null)}
        opportunity={outreach}
      />
    </section>
  )
}
