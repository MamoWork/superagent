import { isRouteErrorResponse, Link, useRouteError } from 'react-router-dom'
import { EmptyState } from '../components/StateViews'

export function RouteError() {
  const error = useRouteError()
  const message = isRouteErrorResponse(error)
    ? `${error.status} ${error.statusText}`
    : error instanceof Error
      ? error.message
      : '页面渲染时发生未知错误。'

  return (
    <section className="view active">
      <div className="view-head">
        <div>
          <div className="eyebrow">Error</div>
          <h1>页面出错了</h1>
          <div className="muted">{message}</div>
        </div>
      </div>
      <EmptyState
        title="无法渲染这个页面"
        description="刷新页面重试；如果持续出现，请查看终端中的前端错误日志。"
        action={
          <Link className="btn primary" to="/">
            回到新建采集
          </Link>
        }
      />
    </section>
  )
}
