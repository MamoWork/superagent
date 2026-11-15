import { Link } from 'react-router-dom'
import { EmptyState } from '../components/StateViews'

export function NotFound() {
  return (
    <section className="view active">
      <div className="view-head">
        <div>
          <div className="eyebrow">404</div>
          <h1>页面不存在</h1>
          <div className="muted">链接可能有误，或页面已经迁移。</div>
        </div>
      </div>
      <EmptyState
        title="没有找到这个页面"
        description="返回新建采集，或从左侧导航进入已有页面。"
        action={
          <Link className="btn primary" to="/">
            回到新建采集
          </Link>
        }
      />
    </section>
  )
}
