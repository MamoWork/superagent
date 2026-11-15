import { useRef, useState } from 'react'
import type { SavedOpportunity } from '../../api/types'
import { Modal } from '../../components/Modal'
import { useToast } from '../../context/ToastContext'
import {
  buildOutreachTemplate,
  OUTREACH_TONES,
  type OutreachTone,
} from '../../lib/outreach'

export function OutreachDialog({
  opportunity,
  open,
  onClose,
}: {
  opportunity: SavedOpportunity | null
  open: boolean
  onClose: () => void
}) {
  if (!open || !opportunity) return null
  return (
    <OutreachDialogBody
      key={opportunity.run_id}
      opportunity={opportunity}
      onClose={onClose}
    />
  )
}

function OutreachDialogBody({
  opportunity,
  onClose,
}: {
  opportunity: SavedOpportunity
  onClose: () => void
}) {
  const { toast } = useToast()
  const textarea = useRef<HTMLTextAreaElement>(null)
  const [tone, setTone] = useState<OutreachTone>('direct')
  const [text, setText] = useState(() =>
    buildOutreachTemplate(opportunity, 'direct'),
  )

  const changeTone = (next: OutreachTone) => {
    setTone(next)
    setText(buildOutreachTemplate(opportunity, next))
  }

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text)
      toast('已复制，请到对应平台手动发送')
    } catch {
      textarea.current?.select()
      toast('无法访问剪贴板，请手动选择复制。', 'error')
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title={`人工触达模板 · ${opportunity.title}`}
      badge={<span className="badge ghost">非 AI 生成</span>}
      maxWidth={640}
      footer={
        <>
          <button type="button" className="btn" onClick={onClose}>
            关闭
          </button>
          <button
            type="button"
            className="btn primary"
            onClick={copy}
            disabled={!text}
          >
            复制模板
          </button>
        </>
      }
    >
      <div className="field" style={{ margin: '12px 0 10px' }}>
        <label className="field-label" htmlFor="outreachTone">
          语气
        </label>
        <select
          id="outreachTone"
          value={tone}
          onChange={(event) => changeTone(event.target.value as OutreachTone)}
        >
          {OUTREACH_TONES.map((item) => (
            <option value={item.value} key={item.value}>
              {item.label}
            </option>
          ))}
        </select>
      </div>
      <textarea
        id="outreachText"
        ref={textarea}
        style={{ minHeight: 210 }}
        value={text}
        onChange={(event) => setText(event.target.value)}
      />
      <p className="hint" style={{ marginTop: 9 }}>
        这是根据机会标题、目标用户和首条公开引用生成的模板，<b>不是 AI 草稿</b>。
        本工具不会自动私信、发帖或发送邮件；请在对应平台由你本人手动发送，并遵守平台的频率与反垃圾规则。
      </p>
    </Modal>
  )
}
