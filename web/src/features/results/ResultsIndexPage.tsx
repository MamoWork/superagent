import { Link, Navigate } from 'react-router-dom'
import { EmptyState, ErrorState, LoadingState } from '../../components/StateViews'
import { useRuns } from '../../hooks/useRuns'
import { getErrorMessage } from '../../lib/errors'

export function ResultsIndexPage() {
  const runs = useRuns(1)

  if (runs.isLoading) {
    return (
      <section className="view active">
        <LoadingState label="查找最近一次分析…" />
      </section>
    )
  }

  if (runs.isError) {
    return (
      <section className="view active">
        <ErrorState
          title="无法读取采集记录"
          message={getErrorMessage(runs.error)}
          onRetry={() => void runs.refetch()}
        />
      </section>
    )
  }

  const latest = runs.data?.runs[0]
  if (latest) {
    return <Navigate to={`/results/${latest.id}`} replace />
  }

  return (
    <section className="view active">
      <div className="view-head">
        <div>
          <div className="eyebrow">Opportunity Analysis</div>
          <h1>机会分析</h1>
          <div className="muted">先发起一次采集，分析结果会显示在这里。</div>
        </div>
        <div className="head-actions">
          <Link className="btn primary" to="/">
            新建采集
          </Link>
        </div>
      </div>
      <EmptyState
        title="还没有采集记录"
        description="在「新建采集」输入方向并运行，完成后会自动跳转到分析页。"
        action={
          <Link className="btn primary" to="/">
            开始第一次采集
          </Link>
        }
      />
    </section>
  )
}
