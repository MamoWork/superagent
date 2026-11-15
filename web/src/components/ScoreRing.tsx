import type { CSSProperties } from 'react'
import { scoreColor } from '../lib/status'

export function ScoreRing({ score }: { score: number }) {
  const style = {
    '--score': score,
    '--ring': scoreColor(score),
  } as CSSProperties
  return (
    <div className="score-ring" style={style} aria-label={`机会评分 ${score}`}>
      <div className="inner">{score}</div>
    </div>
  )
}
