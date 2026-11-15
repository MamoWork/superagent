import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ConfirmDialog } from '../../components/ConfirmDialog'
import { EmptyState, ErrorState, LoadingState } from '../../components/StateViews'
import { useToast } from '../../context/ToastContext'
import { providerName } from '../../data/sourceCatalog'
import { useAIStatus, useProviders } from '../../hooks/useBackend'
import {
  useDeleteSchedule,
  useRunScheduleNow,
  useSchedules,
  useToggleSchedule,
} from '../../hooks/useSchedules'
import { cronLabel, nextRunSortValue } from '../../lib/cron'
import { getErrorMessage } from '../../lib/errors'
import { formatDateTime, isToday } from '../../lib/format'
import type { Schedule } from '../../api/types'
import { ScheduleDialog } from './ScheduleDialog'

export function SchedulesPage() {
  const navigate = useNavigate()
  const { toast } = useToast()
  const schedules = useSchedules()
  const providers = useProviders()
  const ai = useAIStatus()
  const toggle = useToggleSchedule()
  const remove = useDeleteSchedule()
  const runNow = useRunScheduleNow()

  const [dialogOpen, setDialogOpen] = useState(false)
  const [editing, setEditing] = useState<Schedule | null>(null)
  const [deleting, setDeleting] = useState<Schedule | null>(null)

  const items = useMemo(
    () => schedules.data?.schedules ?? [],
    [schedules.data],
  )
  const stats = useMemo(() => {
    const enabled = items.filter((item) => item.enabled)
    const ranToday = items.filter((item) => isToday(item.last_run_at))
    const next = enabled
      .map((item) => item.next_run_at)
      .filter((value): value is string => Boolean(value))
      .sort((a, b) => nextRunSortValue(a).localeCompare(nextRunSortValue(b)))[0]
    return { enabled, ranToday, next }
  }, [items])

  const triggerRun = (schedule: Schedule) => {
    runNow.mutate(schedule.id, {
      onSuccess: (run) => {
        toast(`运行完成：${run.signals.length} 条信号`)
        navigate(`/results/${run.id}`)
      },
      onError: (error) =>
        toast(`运行失败：${getErrorMessage(error)}`, 'error'),
    })
  }

  const runFirst = () => {
    const target = items.find((item) => item.enabled)
    if (!target) {
      toast('没有启用中的定时任务', 'error')
      return
    }
    triggerRun(target)
  }

  const toggleSchedule = (schedule: Schedule, enabled: boolean) => {
    toggle.mutate(
      { id: schedule.id, enabled },
      {
        onSuccess: () => toast(enabled ? '任务已启用' : '任务已暂停'),
        onError: (error) =>
          toast(`更新失败：${getErrorMessage(error)}`, 'error'),
      },
    )
  }

  return (
    <section className="view active">
      <div className="view-head">
        <div>
          <div className="eyebrow">Local Scheduler</div>
          <h1>定时任务</h1>
          <div className="muted">
            按频率自动采集与分析，结果保存在本机；每条结果保留来源链接。
          </div>
        </div>
        <div className="head-actions">
          <button
            className="btn"
            type="button"
            onClick={runFirst}
            disabled={!stats.enabled.length || runNow.isPending}
          >
            立即运行首个任务
          </button>
          <button
            className="btn primary"
            type="button"
            onClick={() => {
              setEditing(null)
              setDialogOpen(true)
            }}
          >
            新建定时任务
          </button>
        </div>
      </div>

      <div className="run-stats">
        <div className="stat">
          <div className="label">启用中的任务</div>
          <div className="value">{stats.enabled.length}</div>
        </div>
        <div className="stat">
          <div className="label">今日已运行</div>
          <div className="value">{stats.ranToday.length}</div>
        </div>
        <div className="stat">
          <div className="label">任务总数</div>
          <div className="value">{items.length}</div>
        </div>
        <div className="stat">
          <div className="label">下次运行</div>
          <div className="value" style={{ fontSize: 18, paddingTop: 5 }}>
            {formatDateTime(stats.next)}
          </div>
        </div>
      </div>

      {schedules.isLoading ? (
        <LoadingState label="加载定时任务…" />
      ) : schedules.isError ? (
        <ErrorState
          title="无法读取定时任务"
          message={getErrorMessage(schedules.error)}
          onRetry={() => void schedules.refetch()}
        />
      ) : items.length ? (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>任务</th>
                <th>方向</th>
                <th>来源</th>
                <th>频率</th>
                <th>下次运行</th>
                <th>上次结果</th>
                <th>启用</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {items.map((schedule) => (
                <tr key={schedule.id}>
                  <td className="sched-task">
                    <b>{schedule.name || schedule.direction}</b>
                    <div className="sched-sub">
                      AI: {ai.data?.configured ? ai.data.model || '已配置' : '未配置'}
                    </div>
                  </td>
                  <td>{schedule.direction}</td>
                  <td>
                    {schedule.provider_ids
                      .map((id) => providerName(providers.data?.providers, id))
                      .join(' · ')}
                  </td>
                  <td>{cronLabel(schedule.cron)}</td>
                  <td>{formatDateTime(schedule.next_run_at)}</td>
                  <td>
                    {schedule.last_error ? (
                      <span className="text-error" title={schedule.last_error}>
                        失败：{schedule.last_error}
                      </span>
                    ) : schedule.last_run_at ? (
                      `已运行 · ${formatDateTime(schedule.last_run_at)}`
                    ) : (
                      '—'
                    )}
                  </td>
                  <td>
                    <label className="toggle">
                      <input
                        type="checkbox"
                        checked={schedule.enabled}
                        onChange={(event) =>
                          toggleSchedule(schedule, event.target.checked)
                        }
                      />
                      <span />
                    </label>
                  </td>
                  <td>
                    <div className="row-actions">
                      <button
                        className="btn ghost small"
                        type="button"
                        onClick={() => {
                          setEditing(schedule)
                          setDialogOpen(true)
                        }}
                      >
                        编辑
                      </button>
                      <button
                        className="btn ghost small"
                        type="button"
                        onClick={() => triggerRun(schedule)}
                        disabled={!schedule.enabled || runNow.isPending}
                      >
                        运行
                      </button>
                      <button
                        className="btn ghost small"
                        type="button"
                        onClick={() => setDeleting(schedule)}
                      >
                        删除
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyState
          title="暂无定时任务"
          description="新建任务后，API 运行期间会按 cron 自动采集；进程退出后不执行、不补跑。"
          action={
            <button
              className="btn primary"
              type="button"
              onClick={() => {
                setEditing(null)
                setDialogOpen(true)
              }}
            >
              新建定时任务
            </button>
          }
        />
      )}

      <div className="panel" style={{ marginTop: 16 }}>
        <div className="panel-head">
          <h2>调度说明</h2>
          <span className="badge ghost">进程内</span>
        </div>
        <p className="hint" style={{ margin: 0 }}>
          调度由 FastAPI 进程内的 APScheduler
          执行：API 运行时按 cron 触发，进程退出后不执行、不补跑。系统级后台常驻、开机自启和桌面通知尚未接入。
        </p>
        <p className="hint" style={{ margin: '8px 0 0' }}>
          任务配置与运行记录保存在本机 SQLite；同一任务不会并发执行。配置了 AI
          模型时，定时采集完成后会自动分析。
        </p>
      </div>

      <ScheduleDialog
        open={dialogOpen}
        onClose={() => {
          setDialogOpen(false)
          setEditing(null)
        }}
        schedule={editing}
      />

      <ConfirmDialog
        open={Boolean(deleting)}
        title="删除定时任务"
        message={`确定删除「${deleting?.name || deleting?.direction || ''}」？已有的采集记录会保留。`}
        confirmLabel="删除"
        pending={remove.isPending}
        onClose={() => setDeleting(null)}
        onConfirm={() => {
          if (!deleting) return
          remove.mutate(deleting.id, {
            onSuccess: () => {
              toast('定时任务已删除')
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
