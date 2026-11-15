import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getProviderHealth, shutdownApp } from '../../api/endpoints'
import { queryKeys } from '../../api/queryKeys'
import { DESKTOP_TOKEN, API_BASE } from '../../api/client'
import type { ProviderInfo, ProviderStatus } from '../../api/types'
import { EmptyState, ErrorState, LoadingState } from '../../components/StateViews'
import { useToast } from '../../context/ToastContext'
import {
  useAIStatus,
  useAppInfo,
  useBackend,
  useProviders,
} from '../../hooks/useBackend'
import { getErrorMessage } from '../../lib/errors'
import { providerStatusLabel } from '../../lib/status'

const AUTH_LABELS = {
  none: '免登录',
  browser: '浏览器登录',
  api_key: 'API Key',
}

const COST_LABELS = {
  free: '免费 / 公开',
  byo_key: '自带 Key',
  paid: '付费',
}

function statusTone(status: ProviderStatus): 'high' | 'verify' | 'ghost' {
  if (status === 'ready') return 'high'
  if (status === 'degraded' || status === 'needs_auth') return 'verify'
  return 'ghost'
}

function ProviderRow({
  provider,
  healthDetail,
}: {
  provider: ProviderInfo
  healthDetail?: string
}) {
  return (
    <div className="provider">
      <div className="provider-head">
        <span className="name">{provider.name}</span>
        <span className={`badge ${statusTone(provider.status)}`}>
          {providerStatusLabel(provider.status)}
        </span>
      </div>
      <div className="provider-fields">
        <div>
          <span>Provider ID</span>
          <code>{provider.id}</code>
        </div>
        <div>
          <span>认证</span>
          <span>{AUTH_LABELS[provider.auth]}</span>
        </div>
        <div>
          <span>能力</span>
          <span>{provider.capabilities.join(' / ')}</span>
        </div>
        <div>
          <span>成本</span>
          <span>{COST_LABELS[provider.cost]}</span>
        </div>
      </div>
      {provider.note ? <p className="hint">{provider.note}</p> : null}
      {healthDetail ? <p className="hint">健康检查：{healthDetail}</p> : null}
    </div>
  )
}

export function SettingsPage() {
  const { toast } = useToast()
  const { online, loading } = useBackend()
  const ai = useAIStatus()
  const appInfo = useAppInfo()
  const providers = useProviders()
  const [quitting, setQuitting] = useState(false)
  const [quitDone, setQuitDone] = useState(false)

  const health = useQuery({
    queryKey: queryKeys.providerHealth,
    queryFn: getProviderHealth,
    enabled: false,
    retry: 0,
    refetchOnWindowFocus: false,
  })

  const copy = async (value: string, label: string) => {
    try {
      await navigator.clipboard.writeText(value)
      toast(`已复制${label}`)
    } catch {
      toast('无法访问剪贴板', 'error')
    }
  }

  const checkAI = async () => {
    try {
      const result = await ai.refetch()
      const data = result.data
      toast(
        data?.configured
          ? `AI 已配置：${data.model}（仅检查后端配置，未发送模型请求）`
          : 'API 已连接，但未配置 AI 模型',
      )
    } catch (error) {
      toast(`检查失败：${getErrorMessage(error)}`, 'error')
    }
  }

  const checkProviders = async () => {
    try {
      const result = await health.refetch()
      if (result.error) throw result.error
      toast('数据源健康检查已更新')
    } catch (error) {
      toast(`检查失败：${getErrorMessage(error)}`, 'error')
    }
  }

  const quit = async () => {
    setQuitting(true)
    try {
      await shutdownApp()
      setQuitDone(true)
      toast('本地服务已退出，可以关闭此页面')
    } catch (error) {
      toast(`退出失败：${getErrorMessage(error)}`, 'error')
      setQuitting(false)
    }
  }

  const healthMap = new Map(
    (health.data?.providers ?? []).map((item) => [item.id, item.detail]),
  )

  return (
    <section className="view active">
      <div className="view-head">
        <div>
          <div className="eyebrow">Settings</div>
          <h1>设置</h1>
          <div className="muted">
            AI 密钥只从后端环境变量读取；本页只展示状态，不收集或保存密钥。
          </div>
        </div>
      </div>

      {!online && !loading ? (
        <div className="panel">
          <ErrorState
            title="API 未连接"
            message="设置页需要读取后端配置。启动本地服务后重试。"
          />
        </div>
      ) : null}

      <div className="settings-grid">
        <div>
          <div className="panel">
            <div className="panel-head">
              <h2>AI 引擎</h2>
              <span
                className={`badge ${ai.data?.configured ? 'high' : 'ghost'}`}
              >
                {ai.isLoading
                  ? '检测中'
                  : ai.data?.configured
                    ? '已配置'
                    : '未配置'}
              </span>
            </div>
            <p className="hint" style={{ margin: '0 0 12px' }}>
              后端从环境变量读取 <code>OPPORTUNITY_AI_MODEL</code> /{' '}
              <code>OPPORTUNITY_AI_API_KEY</code>；密钥不写入数据库。此页仅展示连接状态。
            </p>

            {ai.isError ? (
              <ErrorState
                title="无法读取 AI 状态"
                message={getErrorMessage(ai.error)}
                onRetry={() => void ai.refetch()}
              />
            ) : ai.isLoading ? (
              <LoadingState label="检测 AI 配置…" />
            ) : (
              <div className="provider default">
                <div className="provider-head">
                  <span className="name">当前后端配置</span>
                  <span
                    className={`badge ${ai.data?.configured ? 'high' : 'ghost'}`}
                  >
                    {ai.data?.configured ? '已配置' : '未配置'}
                  </span>
                </div>
                <div className="field">
                  <label>Provider</label>
                  <input readOnly value={ai.data?.provider || '—'} />
                </div>
                <div className="field">
                  <label>Model</label>
                  <input readOnly value={ai.data?.model || '—'} />
                </div>
                <div className="field">
                  <label>Base URL</label>
                  <input readOnly value={ai.data?.base_url || '—'} />
                </div>
                <div className="field">
                  <label>API Key</label>
                  <input
                    readOnly
                    value="由后端环境变量提供，不在此页面读取或保存"
                  />
                </div>
                {ai.data?.note ? (
                  <p className="hint" style={{ marginTop: 8 }}>
                    {ai.data.note}
                  </p>
                ) : null}
              </div>
            )}

            <p className="hint" style={{ margin: '0 0 12px' }}>
              切换模型请修改 API 进程的启动环境：
              <code>OPPORTUNITY_AI_MODEL</code>、
              <code>OPPORTUNITY_AI_BASE_URL</code>、
              <code>OPPORTUNITY_AI_API_KEY</code>。完整示例见{' '}
              <code>server/README.md</code>。
            </p>

            <div className="settings-actions">
              <button className="btn" type="button" onClick={checkAI}>
                重新检测配置
              </button>
            </div>
            <p className="hint" style={{ marginTop: 8 }}>
              该按钮只重新读取{' '}
              <code>GET /api/v1/ai/status</code>
              ，不会向模型发送测试请求，也不会上传密钥。
            </p>
          </div>

          <div className="panel">
            <div className="panel-head">
              <h2>获取与合规</h2>
              <span className="badge ghost">固定策略</span>
            </div>
            <div className="toggle-row">
              <div>
                <b>自动私信 / 发帖</b>
                <div className="muted" style={{ fontSize: 11.5 }}>
                  始终禁用：只读采集，避免平台风控
                </div>
              </div>
              <span className="compliance-pill">已禁用</span>
            </div>
            <div className="toggle-row">
              <div>
                <b>触达前人工确认</b>
                <div className="muted" style={{ fontSize: 11.5 }}>
                  模板只提供复制，发送由你本人完成
                </div>
              </div>
              <span className="compliance-pill on">始终启用</span>
            </div>
            <p className="hint" style={{ margin: '10px 0 0' }}>
              线索仅用于合规的商务沟通；请遵守 Reddit
              等平台的频率与反垃圾规则。本页没有可切换的自动化开关。
            </p>
          </div>
        </div>

        <div>
          <div className="panel">
            <div className="panel-head">
              <h2>数据源</h2>
              <span className="badge ghost">后端 Provider Registry</span>
            </div>
            <p className="hint" style={{ margin: '0 0 12px' }}>
              当前可采集的数据源由后端注册表决定。状态为「可用 / 降级可用」的来源才会出现在采集页。
            </p>

            {providers.isLoading ? (
              <LoadingState label="加载数据源…" />
            ) : providers.isError ? (
              <ErrorState
                title="无法读取数据源"
                message={getErrorMessage(providers.error)}
                onRetry={() => void providers.refetch()}
              />
            ) : providers.data?.providers.length ? (
              providers.data.providers.map((provider) => (
                <ProviderRow
                  provider={provider}
                  healthDetail={healthMap.get(provider.id)}
                  key={provider.id}
                />
              ))
            ) : (
              <EmptyState
                title="没有注册的数据源"
                description="检查后端 Provider Registry 配置。"
              />
            )}

            <div className="settings-actions">
              <button
                className="btn"
                type="button"
                onClick={checkProviders}
                disabled={health.isFetching || !online}
              >
                {health.isFetching ? '检查中…' : '检查数据源健康'}
              </button>
            </div>
            {health.isError ? (
              <p className="form-error">
                健康检查失败：{getErrorMessage(health.error)}
              </p>
            ) : null}

            <div className="field" style={{ marginTop: 14 }}>
              <label className="field-label">API Base</label>
              <input
                type="text"
                readOnly
                value={API_BASE}
                style={{ fontSize: 12, background: '#f9fafb', color: '#6b7280' }}
              />
            </div>
            <p className="hint" style={{ marginTop: 6 }}>
              核心与 UI 只调用统一 API；命令行、登录与错误码由适配器内部处理，可替换或新增工具。
            </p>
          </div>

          <div className="panel">
            <div className="panel-head">
              <h2>存储与导出</h2>
              <span className="badge ghost">
                {appInfo.data ? `v${appInfo.data.version}` : '—'}
              </span>
            </div>
            {appInfo.isLoading ? (
              <LoadingState label="读取存储信息…" />
            ) : appInfo.isError ? (
              <ErrorState
                title="无法读取存储信息"
                message={getErrorMessage(appInfo.error)}
                onRetry={() => void appInfo.refetch()}
              />
            ) : (
              <>
                <div className="field">
                  <label className="field-label">SQLite 数据库</label>
                  <input
                    type="text"
                    readOnly
                    value={appInfo.data?.db_path || '—'}
                    style={{
                      fontSize: 12,
                      background: '#f9fafb',
                      color: '#6b7280',
                    }}
                  />
                </div>
                <div className="field" style={{ marginTop: 10 }}>
                  <label className="field-label">数据目录</label>
                  <input
                    type="text"
                    readOnly
                    value={appInfo.data?.data_dir || '—'}
                    style={{
                      fontSize: 12,
                      background: '#f9fafb',
                      color: '#6b7280',
                    }}
                  />
                </div>
                <p className="hint" style={{ margin: '6px 0 0' }}>
                  可通过 <code>OPPORTUNITY_SCOUT_DB</code>{' '}
                  覆盖。导出文件由浏览器下载，不写入固定目录。
                </p>
                <div className="settings-actions">
                  <button
                    className="btn"
                    type="button"
                    onClick={() =>
                      copy(appInfo.data?.db_path || '', '数据路径')
                    }
                  >
                    复制数据库路径
                  </button>
                  {appInfo.data?.desktop && DESKTOP_TOKEN && !quitDone ? (
                    <button
                      className="btn"
                      type="button"
                      onClick={quit}
                      disabled={quitting}
                    >
                      {quitting ? '正在退出…' : '退出本地服务'}
                    </button>
                  ) : null}
                </div>
                {quitDone ? (
                  <p className="hint">本地服务已退出，可以关闭此页面。</p>
                ) : !appInfo.data?.desktop ? (
                  <p className="hint" style={{ marginTop: 8 }}>
                    当前通过开发服务器访问，无法从这里退出；请在运行后端的终端按
                    Ctrl+C 停止进程。
                  </p>
                ) : !DESKTOP_TOKEN ? (
                  <p className="hint" style={{ marginTop: 8 }}>
                    桌面退出令牌未注入，无法退出本地服务。
                  </p>
                ) : null}
              </>
            )}
          </div>
        </div>
      </div>
    </section>
  )
}
