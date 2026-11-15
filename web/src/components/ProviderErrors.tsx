import type { ProviderErrorInfo } from '../api/types'
import { providerName } from '../data/sourceCatalog'
import type { ProviderInfo } from '../api/types'

export function ProviderErrors({
  errors,
  providers,
}: {
  errors: Record<string, ProviderErrorInfo>
  providers: ProviderInfo[] | undefined
}) {
  const entries = Object.entries(errors)
  if (!entries.length) return null
  return (
    <div className="panel provider-errors">
      <div className="panel-head">
        <h2>部分来源未完成</h2>
        <span className="badge verify">{entries.length} 个来源报错</span>
      </div>
      {entries.map(([id, error]) => (
        <div className="provider-error" key={id}>
          <div className="provider-error-head">
            <b>{providerName(providers, id)}</b>
            <code>{error.code}</code>
          </div>
          <p>{error.message}</p>
          {error.hint ? <p className="hint">{error.hint}</p> : null}
          {error.retry_after_seconds ? (
            <p className="hint">
              建议等待 {error.retry_after_seconds} 秒后再试；不要更换账号或后端反复请求。
            </p>
          ) : null}
        </div>
      ))}
    </div>
  )
}
