import { Link } from 'react-router-dom'
import { EmptyState, ErrorState, LoadingState } from '../../components/StateViews'
import { providerName } from '../../data/sourceCatalog'
import { useProviders } from '../../hooks/useBackend'
import { useRuns } from '../../hooks/useRuns'
import { getErrorMessage } from '../../lib/errors'
import { formatDateTime } from '../../lib/format'
import { runStatusMeta } from '../../lib/status'

export function HistoryPage() {
  const runs = useRuns(50)
  const providers = useProviders()

  return (
    <section className="view active">
      <div className="view-head">
        <div>
          <div className="eyebrow">Local History</div>
          <h1>采集历史</h1>
          <div className="muted">所有运行记录保存在本机 SQLite，不上传云端。</div>
        </div>
        <div className="head-actions">
          <Link className="btn primary" to="/">
            新建采集
          </Link>
        </div>
      </div>

      {runs.isLoading ? (
        <LoadingState label="加载采集历史…" />
      ) : runs.isError ? (
        <ErrorState
          title="无法读取采集历史"
          message={getErrorMessage(runs.error)}
          onRetry={() => void runs.refetch()}
        />
      ) : runs.data && runs.data.runs.length ? (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>时间</th>
                <th>方向</th>
                <th>来源</th>
                <th>信号</th>
                <th>AI</th>
                <th>状态</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {runs.data.runs.map((run) => {
                const status = runStatusMeta(run.status)
                return (
                  <tr key={run.id}>
                    <td>{formatDateTime(run.created_at)}</td>
                    <td>{run.direction}</td>
                    <td>
                      {run.provider_ids
                        .map((id) =>
                          providerName(providers.data?.providers, id),
                        )
                        .join(' · ') || '—'}
                    </td>
                    <td>{run.stats.signal_count ?? '—'}</td>
                    <td>
                      {run.has_analysis ? (
                        <span className="state done">
                          <span className="dot" />
                          已分析
                        </span>
                      ) : (
                        '—'
                      )}
                    </td>
                    <td>
                      <span className={`state ${status.className}`}>
                        <span className="dot" />
                        {status.label}
                      </span>
                    </td>
                    <td>
                      <Link className="link" to={`/results/${run.id}`}>
                        查看
                      </Link>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyState
          title="暂无采集记录"
          description="发起一次采集后，记录会自动出现在这里。"
          action={
            <Link className="btn primary" to="/">
              新建采集
            </Link>
          }
        />
      )}
    </section>
  )
}
