import type { ReactNode } from 'react'

export function LoadingState({ label = '加载中…' }: { label?: string }) {
  return (
    <div className="empty-state" role="status">
      <span className="spinner" aria-hidden="true" />
      <b>{label}</b>
    </div>
  )
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string
  description: string
  action?: ReactNode
}) {
  return (
    <div className="empty-state">
      <b>{title}</b>
      <span>{description}</span>
      {action ? <div className="empty-action">{action}</div> : null}
    </div>
  )
}

export function ErrorState({
  title = '加载失败',
  message,
  onRetry,
}: {
  title?: string
  message: string
  onRetry?: () => void
}) {
  return (
    <div className="empty-state error-state" role="alert">
      <b>{title}</b>
      <span>{message}</span>
      {onRetry ? (
        <div className="empty-action">
          <button type="button" className="btn" onClick={onRetry}>
            重试
          </button>
        </div>
      ) : null}
    </div>
  )
}
