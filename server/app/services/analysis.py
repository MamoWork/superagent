from __future__ import annotations

import re

from app.schemas import EvidenceBrief, ProviderErrorInfo, Run, Signal

PAIN_PATTERNS: dict[str, str] = {
    "workaround": r"\b(spreadsheet|excel|manual|by hand|copy|paste|bookmark)\b",
    "search_intent": r"\b(is there a tool|any recommendations|best tool|looking for|alternative|recommend)\b",
    "pain": r"\b(struggling|pain|annoying|waste|time[- ]consuming|expensive|frustrat|hard|difficult)\b",
    "payment": r"\b(pay|paid|subscription|price|budget|per month|/month|\\$)\b",
    "supply": r"\b(supplier|factory|alibaba|1688|moq|sample|shipping|logistics)\b",
    "risk": r"\b(scam|fake|middleman|blocked|ban|risk|customs|compliance)\b",
}


def _signal_score(signal: Signal) -> float:
    score = min(len(signal.quote) / 400.0, 3.0)
    if signal.author_public:
        score += 2.0
    if signal.metrics:
        score += 1.0
    return score


def build_brief(run: Run) -> EvidenceBrief:
    text = " ".join(f"{signal.title} {signal.quote}" for signal in run.signals)
    pain_phrases = {
        name: len(re.findall(pattern, text, flags=re.IGNORECASE))
        for name, pattern in PAIN_PATTERNS.items()
    }
    provider_counts = run.stats.get("provider_counts", {})
    provider_errors = {
        key: ProviderErrorInfo(**value)
        for key, value in run.stats.get("provider_errors", {}).items()
    }
    top_signals = sorted(run.signals, key=_signal_score, reverse=True)[:20]
    return EvidenceBrief(
        run_id=run.id,
        status=run.status,
        signal_count=len(run.signals),
        provider_counts=provider_counts,
        provider_errors=provider_errors,
        top_signals=top_signals,
        pain_phrases=pain_phrases,
        note=(
            "启发式证据包：只统计公开信号中的关键词、来源分布与原文引用，"
            "不构成 AI 机会判断。请人工核对链接与上下文后再决定是否验证。"
        ),
    )


def brief_markdown(run: Run, brief: EvidenceBrief) -> str:
    pack_name = run.stats.get("domain_pack_name")
    pack_label = f"（{pack_name}）" if pack_name else ""
    if "time_range_days" not in run.stats:
        time_label = "未记录"
    else:
        time_range = run.stats.get("time_range_days")
        time_label = f"{time_range} 天" if time_range else "不限"
    lines: list[str] = [
        f"# 机会证据包 · {run.direction}",
        "",
        f"- Run：`{run.id}`",
        f"- 领域包：`{run.domain_pack}`{pack_label}",
        f"- 状态：`{run.status}`",
        f"- 信号数：{brief.signal_count}",
        f"- 时间范围：{time_label}",
        f"- 查询：{run.stats.get('query', '')}",
        f"- 创建时间：{run.created_at}",
        "",
        "## 来源分布",
        "",
        "| 数据源 | 信号数 |",
        "|---|---:|",
    ]
    for provider_id, count in brief.provider_counts.items():
        lines.append(f"| {provider_id} | {count} |")

    if brief.provider_errors:
        lines.extend(["", "## 数据源错误", ""])
        for provider_id, error in brief.provider_errors.items():
            lines.append(
                f"- `{provider_id}` · {error.code}：{error.message}"
                + (f"（{error.hint}）" if error.hint else "")
            )

    lines.extend(["", "## 关键词信号", "", "| 类型 | 命中次数 |", "|---|---:|"])
    for name, count in brief.pain_phrases.items():
        lines.append(f"| {name} | {count} |")

    lines.extend(["", "## 高优先级信号", ""])
    if not brief.top_signals:
        lines.append("没有采集到信号。请检查数据源状态、查询词或平台限流。")
    for index, signal in enumerate(brief.top_signals, start=1):
        title = signal.title or signal.source_url
        lines.append(f"### {index}. {title}")
        lines.append("")
        lines.append(f"- 来源：`{signal.provider_id}`")
        lines.append(f"- 链接：{signal.source_url}")
        if signal.author_public:
            lines.append(f"- 作者：{signal.author_public}")
        if signal.published_at:
            lines.append(f"- 时间：{signal.published_at}")
        if signal.quote:
            quote = signal.quote.strip().replace("\n", " ")
            lines.append("")
            lines.append(f"> {quote[:1500]}")
        lines.append("")

    lines.extend(["---", "", brief.note, ""])
    return "\n".join(lines)
