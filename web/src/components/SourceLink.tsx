import { LinkIcon } from './icons'

export interface SourceLinkData {
  title: string
  url: string
  meta?: string
  quote?: string
}

export function SourceLink({ source }: { source: SourceLinkData }) {
  if (!source.url) return null
  return (
    <a
      className="source-link"
      href={source.url}
      target="_blank"
      rel="noopener noreferrer"
    >
      <LinkIcon className="ico" />
      <span className="src-body">
        <span className="src-title">
          {source.title || source.url} <span className="ext">↗</span>
        </span>
        {source.meta ? <span className="src-meta">{source.meta}</span> : null}
        {source.quote ? <span className="quote">{source.quote}</span> : null}
      </span>
    </a>
  )
}
