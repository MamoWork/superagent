import type { ReactNode } from 'react'
import type { DimensionScore, Verdict } from '../api/types'
import { VerdictBadge } from './Badge'
import { Modal } from './Modal'
import { SourceLink, type SourceLinkData } from './SourceLink'

export interface OpportunityDetailData {
  title: string
  score: number
  verdict: Verdict
  thesis: string
  target_customer: string
  willingness_to_pay: string
  risks: string[]
  next_actions: Array<{ action: string; due_in_days?: number | null }>
  dimension_scores: DimensionScore[]
  missing_information?: string[]
  citations: SourceLinkData[]
}

export function OpportunityDetailDialog({
  open,
  onClose,
  data,
  footer,
}: {
  open: boolean
  onClose: () => void
  data: OpportunityDetailData | null
  footer?: ReactNode
}) {
  if (!data) return null
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={data.title}
      badge={<VerdictBadge verdict={data.verdict} />}
      footer={
        footer ?? (
          <button type="button" className="btn" onClick={onClose}>
            关闭
          </button>
        )
      }
    >
      <div className="detail-block">
        <div className="label">机会评分</div>
        <p>
          <b>{data.score}</b> / 100
        </p>
      </div>
      <div className="detail-block">
        <div className="label">核心判断</div>
        <p>{data.thesis || '—'}</p>
      </div>
      <div className="detail-block">
        <div className="label">目标用户</div>
        <p>{data.target_customer || '—'}</p>
      </div>
      <div className="detail-block">
        <div className="label">付费信号</div>
        <p>{data.willingness_to_pay || '—'}</p>
      </div>
      <div className="detail-block">
        <div className="label">风险与反证</div>
        {data.risks.length ? (
          <ul className="detail-list">
            {data.risks.map((risk) => (
              <li key={risk}>{risk}</li>
            ))}
          </ul>
        ) : (
          <p>—</p>
        )}
      </div>
      <div className="detail-block">
        <div className="label">下一步</div>
        {data.next_actions.length ? (
          <ul className="detail-list">
            {data.next_actions.map((action, index) => (
              <li key={`${action.action}-${index}`}>
                {action.action}
                {action.due_in_days ? `（${action.due_in_days} 天内）` : ''}
              </li>
            ))}
          </ul>
        ) : (
          <p>—</p>
        )}
      </div>
      {data.dimension_scores.length ? (
        <div className="detail-block">
          <div className="label">评分维度</div>
          <div className="dimension-list">
            {data.dimension_scores.map((dimension) => (
              <div className="dimension-row" key={dimension.dimension_id}>
                <div className="dimension-head">
                  <b>{dimension.name}</b>
                  <span>
                    {dimension.score}/10 · 权重{' '}
                    {Math.round(dimension.weight * 100)}%
                  </span>
                </div>
                <div className="mini-progress">
                  <span style={{ width: `${dimension.score * 10}%` }} />
                </div>
                <p>{dimension.rationale || '—'}</p>
              </div>
            ))}
          </div>
        </div>
      ) : null}
      {data.missing_information?.length ? (
        <div className="detail-block">
          <div className="label">仍缺的信息</div>
          <ul className="detail-list">
            {data.missing_information.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      ) : null}
      <div className="detail-block">
        <div className="label">全部来源链接</div>
        {data.citations.length ? (
          data.citations.map((citation, index) => (
            <SourceLink
              source={citation}
              key={`${citation.url}-${index}`}
            />
          ))
        ) : (
          <p>没有可核对的引用。</p>
        )}
      </div>
    </Modal>
  )
}
