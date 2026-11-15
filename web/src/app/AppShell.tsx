import { Outlet } from 'react-router-dom'
import { useBackend } from '../hooks/useBackend'
import { ScrollToTop } from './ScrollToTop'
import { Sidebar } from './Sidebar'
import { Topbar } from './Topbar'

export function AppShell() {
  const { online, loading, refresh } = useBackend()

  return (
    <div className="app">
      <ScrollToTop />
      <Sidebar />
      <main className="main">
        <Topbar />
        {!loading && !online ? (
          <div className="offline-banner" role="alert">
            <span>
              API 未连接。页面只展示本地已有状态；采集、分析、保存与调度等写操作不可用。
            </span>
            <button type="button" className="btn small" onClick={refresh}>
              重试连接
            </button>
          </div>
        ) : null}
        <Outlet />
      </main>
    </div>
  )
}
