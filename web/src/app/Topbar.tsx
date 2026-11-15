import { Link, useLocation } from 'react-router-dom'
import { useBackend } from '../hooks/useBackend'

const PAGE_NAMES: Array<[RegExp, string]> = [
  [/^\/$/, '新建采集'],
  [/^\/results/, '机会分析'],
  [/^\/pipeline/, '获取闭环'],
  [/^\/schedules/, '定时任务'],
  [/^\/history/, '采集历史'],
  [/^\/library/, '机会库'],
  [/^\/settings/, '设置'],
]

export function Topbar() {
  const { online, loading, ai, refresh } = useBackend()
  const location = useLocation()
  const current =
    PAGE_NAMES.find(([pattern]) => pattern.test(location.pathname))?.[1] ??
    '未找到页面'

  const dotColor = loading ? '#94a3b8' : online ? '#34d399' : '#f59e0b'
  const aiText = ai.data?.configured
    ? `AI：${ai.data.model || ai.data.provider || '已配置'}`
    : 'AI：未配置'

  return (
    <header className="topbar">
      <div className="crumb">
        工作台 / <b>{current}</b>
      </div>
      <div className="top-actions">
        <button
          type="button"
          className="status-chip"
          title={online ? '点击重新检测 API' : '点击重试连接 API'}
          onClick={refresh}
        >
          <span className="dot" style={{ background: dotColor }} />
          {loading ? (
            <>API：<b>检测中</b></>
          ) : online ? (
            <>API：已连接 · <b>{aiText}</b></>
          ) : (
            <>API：<b>未连接</b></>
          )}
        </button>
        <Link className="btn small" to="/settings">
          设置
        </Link>
      </div>
    </header>
  )
}
