from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from typing import Protocol

import httpx

from app.config import Settings
from app.db import Database
from app.domain_packs import DomainPack, get_pack
from app.schemas import (
    AIStatus,
    AnalysisDraft,
    Citation,
    CitationDraft,
    DimensionScore,
    NextAction,
    OpportunityAnalysis,
    Run,
    Signal,
)


class AnalysisError(Exception):
    """The AI engine could not produce a usable analysis."""


class AnalysisNotConfigured(AnalysisError):
    """No usable model/key is configured."""


class AnalysisEngine(Protocol):
    name: str

    async def draft(self, run: Run, pack: DomainPack) -> AnalysisDraft: ...


SYSTEM_PROMPT = """你是一名严谨的商机研究员。你的任务不是写营销文案，而是根据公开证据判断一个机会是否值得投入。

硬性规则：
1. 只能使用用户提供的信号。不得编造事实、数字、客户、竞品、链接或引用。
2. 每个评分维度的理由都要尽量引用 signal_id；引用必须来自输入信号。
3. 证据不足时给低分，并把缺口写进 missing_information，不要用常识补齐。
4. 公开网页结果不保证站内全量，不要把“没搜到”当成“不存在”。
5. 用中文输出，严格返回 JSON。"""


def _clean(text: str | None, limit: int = 4000) -> str:
    text = (text or "").replace("\x00", " ").strip()
    return text[:limit]


def _select_signals(
    run: Run,
    max_signals: int,
    max_chars_per_signal: int,
    max_total_chars: int,
) -> list[Signal]:
    ordered = sorted(
        run.signals,
        key=lambda signal: (
            len(signal.quote),
            bool(signal.author_public),
            bool(signal.metrics),
        ),
        reverse=True,
    )
    selected: list[Signal] = []
    used = 0
    for signal in ordered[:max_signals]:
        block_len = min(len(signal.quote), max_chars_per_signal) + len(signal.title) + 160
        if selected and used + block_len > max_total_chars:
            break
        selected.append(signal)
        used += block_len
    return selected


def build_prompt(
    run: Run,
    pack: DomainPack,
    max_signals: int = 40,
    max_chars_per_signal: int = 1200,
    max_total_chars: int = 30000,
) -> str:
    signals = _select_signals(
        run, max_signals, max_chars_per_signal, max_total_chars
    )
    scorecard = "\n".join(
        f"- {dim.id} | {dim.name} | 权重 {dim.weight:.0%} | {dim.description}"
        for dim in pack.scorecard
    )
    signal_blocks = []
    for signal in signals:
        quote = _clean(signal.quote, max_chars_per_signal)
        signal_blocks.append(
            "\n".join(
                [
                    f"[signal_id={signal.id}]",
                    f"provider: {signal.provider_id}",
                    f"source_type: {signal.source_type}",
                    f"title: {_clean(signal.title, 300)}",
                    f"author: {signal.author_public or '未知'}",
                    f"published_at: {signal.published_at or '未知'}",
                    f"quote: {quote or '（无正文）'}",
                ]
            )
        )
    signal_text = "\n\n".join(signal_blocks) or "（没有可用信号）"

    return f"""## 领域包
名称：{pack.name}
说明：{pack.description}

评分卡（dimension_id | 名称 | 权重 | 打分标准）：
{scorecard}

输出 dimensions 时必须覆盖以上所有 dimension_id，score 为 0-10 的整数。

## 研究主题
方向：{run.direction}
关键词：{", ".join(run.keywords) or "无"}
时间范围：{run.stats.get("time_range_days", "未记录")} 天
数据源：{", ".join(run.provider_ids)}

## 输入信号（共 {len(signals)} 条，来自公开网页）
{signal_text}

## 返回格式
严格返回一个 JSON 对象，不要 Markdown 代码块，不要额外说明：
{{
  "one_liner": "一句话判断，不超过 60 字",
  "thesis": "机会逻辑与反证，必须基于信号",
  "target_customer": "最具体的首批目标客户",
  "willingness_to_pay": "付费意愿判断及依据；没有证据就说明没有证据",
  "dimensions": [
    {{
      "dimension_id": "评分卡中的 id",
      "score": 0,
      "rationale": "为什么是这个分数",
      "citations": [{{"signal_id": "输入信号 id", "quote": "原文短引用，最多 300 字"}}]
    }}
  ],
  "next_actions": ["下一步可执行动作，最多 5 条"],
  "risks": ["主要风险，最多 5 条"],
  "missing_information": ["还缺什么证据，最多 8 条"]
}}"""


def _extract_json(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise AnalysisError("AI 返回中没有 JSON 对象。")
    return text[start : end + 1]


class OpenAICompatibleEngine:
    """Uses the official OpenAI Python SDK, so any OpenAI-compatible endpoint works."""

    def __init__(
        self,
        model: str,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float = 120.0,
    ) -> None:
        self.name = model
        self.model = model
        self.base_url = (
            base_url or os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1"
        )
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.timeout = timeout
        if not self.api_key:
            raise AnalysisNotConfigured(
                "未配置 API Key。请设置 OPENAI_API_KEY 或 OPPORTUNITY_AI_API_KEY。"
            )

    async def draft(self, run: Run, pack: DomainPack) -> AnalysisDraft:
        from openai import APIStatusError, AsyncOpenAI, BadRequestError

        client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=self.timeout,
        )
        prompt = build_prompt(run, pack)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        try:
            try:
                response = await client.beta.chat.completions.parse(
                    model=self.model,
                    messages=messages,
                    response_format=AnalysisDraft,
                    temperature=0.2,
                )
                parsed = response.choices[0].message.parsed
                if parsed is not None:
                    return parsed
            except (BadRequestError, TypeError, AttributeError):
                # Some OpenAI-compatible gateways do not support json_schema.
                response = await client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    response_format={"type": "json_object"},
                    temperature=0.2,
                )
                content = response.choices[0].message.content or ""
                return AnalysisDraft.model_validate_json(_extract_json(content))
        except AnalysisError:
            raise
        except APIStatusError as exc:
            raise AnalysisError(
                f"AI 引擎返回 {exc.status_code}：{exc.message[:300]}"
            ) from exc
        except Exception as exc:  # network, timeout, invalid JSON from provider
            raise AnalysisError(f"AI 引擎调用失败：{exc}") from exc
        finally:
            await client.close()


class AnthropicEngine:
    """Minimal Messages API client; no SDK dependency is required."""

    def __init__(
        self,
        model: str,
        base_url: str = "https://api.anthropic.com",
        api_key: str | None = None,
        timeout: float = 120.0,
    ) -> None:
        self.name = f"anthropic:{model}"
        self.model = model.removeprefix("anthropic:")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.timeout = timeout
        if not self.api_key:
            raise AnalysisNotConfigured(
                "未配置 Anthropic API Key。请设置 ANTHROPIC_API_KEY 或 "
                "OPPORTUNITY_AI_API_KEY。"
            )

    async def draft(self, run: Run, pack: DomainPack) -> AnalysisDraft:
        prompt = build_prompt(run, pack)
        payload = {
            "model": self.model,
            "max_tokens": 4096,
            "temperature": 0.2,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": prompt}],
        }
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/v1/messages", json=payload, headers=headers
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            raise AnalysisError(
                f"Anthropic 返回 {exc.response.status_code}：{exc.response.text[:300]}"
            ) from exc
        except httpx.HTTPError as exc:
            raise AnalysisError(f"Anthropic 调用失败：{exc}") from exc

        text = "".join(
            block.get("text", "")
            for block in data.get("content", [])
            if block.get("type") == "text"
        )
        try:
            return AnalysisDraft.model_validate_json(_extract_json(text))
        except Exception as exc:
            raise AnalysisError(f"Anthropic 返回无法解析为分析结果：{exc}") from exc


def _provider_for(settings: Settings, model: str) -> str:
    provider = (settings.ai_provider or "auto").strip().lower()
    if provider != "auto":
        return provider
    if model.startswith("anthropic:") or model.startswith("claude"):
        return "anthropic"
    if model.startswith("ollama:"):
        return "ollama"
    return "openai"


def build_engine(
    settings: Settings, model_override: str | None = None
) -> AnalysisEngine | None:
    model = (model_override or settings.ai_model or "").strip()
    if not model:
        return None
    provider = _provider_for(settings, model)
    api_key = settings.ai_api_key
    if provider in {"anthropic", "claude"}:
        return AnthropicEngine(
            model=model,
            base_url=settings.ai_base_url or "https://api.anthropic.com",
            api_key=api_key,
            timeout=settings.ai_timeout,
        )
    if provider in {"openai", "openai-compatible", "ollama", "deepseek", "qwen", "custom"}:
        base_url = settings.ai_base_url
        if provider == "ollama" and not base_url:
            base_url = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1")
        if not api_key and provider == "ollama":
            api_key = "ollama"
        return OpenAICompatibleEngine(
            model=model.removeprefix("openai:").removeprefix("ollama:"),
            base_url=base_url,
            api_key=api_key,
            timeout=settings.ai_timeout,
        )
    raise AnalysisNotConfigured(f"不支持的 AI 引擎：{provider}")


def ai_status(settings: Settings) -> AIStatus:
    if not settings.ai_model:
        return AIStatus(
            configured=False,
            note="未配置 AI 模型。设置 OPPORTUNITY_AI_MODEL 后启用分析。",
        )
    provider = _provider_for(settings, settings.ai_model)
    if provider in {"anthropic", "claude"}:
        has_key = bool(settings.ai_api_key or os.environ.get("ANTHROPIC_API_KEY"))
        model = settings.ai_model.removeprefix("anthropic:")
    elif provider == "ollama":
        has_key = True
        model = settings.ai_model.removeprefix("ollama:")
    else:
        has_key = bool(settings.ai_api_key or os.environ.get("OPENAI_API_KEY"))
        model = settings.ai_model.removeprefix("openai:")
    return AIStatus(
        configured=has_key,
        provider=provider,
        model=model,
        base_url=settings.ai_base_url,
        note=(
            "已配置。密钥只从环境变量读取，不写入数据库。"
            if has_key
            else "缺少 API Key，请设置 OPPORTUNITY_AI_API_KEY 或对应厂商的环境变量。"
        ),
    )


def _resolve_citations(
    drafts: list[CitationDraft], known: dict[str, Signal]
) -> list[Citation]:
    resolved: list[Citation] = []
    seen: set[str] = set()
    for item in drafts:
        signal = known.get(item.signal_id)
        if signal is None or signal.id in seen:
            continue
        seen.add(signal.id)
        quote = _clean(item.quote, 300) or _clean(signal.quote, 300)
        resolved.append(
            Citation(
                signal_id=signal.id,
                source_url=signal.source_url,
                quote=quote,
            )
        )
    return resolved


def _finalize(
    run: Run,
    pack: DomainPack,
    draft: AnalysisDraft,
    model: str,
) -> OpportunityAnalysis:
    known = {signal.id: signal for signal in run.signals}
    draft_dimensions = {
        item.dimension_id.strip().lower(): item for item in draft.dimensions
    }

    dimension_scores: list[DimensionScore] = []
    weighted_total = 0.0
    confidence_score: int | None = None
    for dimension in pack.scorecard:
        item = draft_dimensions.get(dimension.id)
        score = max(0, min(10, item.score)) if item else 0
        rationale = _clean(item.rationale, 2000) if item else "模型未给出该维度评分。"
        citations = _resolve_citations(item.citations, known) if item else []
        points = round(score / 10 * dimension.weight * 100, 1)
        weighted_total += points
        if dimension.id == "confidence":
            confidence_score = score
        dimension_scores.append(
            DimensionScore(
                dimension_id=dimension.id,
                name=dimension.name,
                weight=dimension.weight,
                score=score,
                weighted_points=points,
                rationale=rationale,
                citations=citations,
            )
        )

    score = int(round(weighted_total))
    all_citations: list[Citation] = []
    seen: set[str] = set()
    for dimension in dimension_scores:
        for citation in dimension.citations:
            if citation.signal_id not in seen:
                seen.add(citation.signal_id)
                all_citations.append(citation)

    verdict: str
    if score >= 70:
        verdict = "build"
    elif score >= 50:
        verdict = "verify"
    else:
        verdict = "drop"

    # Low evidence confidence or no traceable citation must never produce "build".
    if verdict == "build" and (
        not all_citations or (confidence_score is not None and confidence_score < 5)
    ):
        verdict = "verify"

    missing = [_clean(item, 500) for item in draft.missing_information if _clean(item)]
    if not all_citations:
        missing.append("没有可核对的原文引用；请先补充原始链接，再判断是否投入。")

    return OpportunityAnalysis(
        run_id=run.id,
        domain_pack=pack.id,
        verdict=verdict,  # type: ignore[arg-type]
        score=score,
        one_liner=_clean(draft.one_liner, 160),
        thesis=_clean(draft.thesis, 4000),
        target_customer=_clean(draft.target_customer, 1000),
        willingness_to_pay=_clean(draft.willingness_to_pay, 1000),
        dimension_scores=dimension_scores,
        next_actions=[
            NextAction(action=_clean(action, 500))
            for action in draft.next_actions
            if _clean(action)
        ][:5],
        risks=[_clean(risk, 500) for risk in draft.risks if _clean(risk)][:5],
        missing_information=missing[:8],
        citations=all_citations[:20],
        model=model,
        created_at=datetime.now(timezone.utc).isoformat(),
    )


async def analyze_run(
    db: Database,
    run: Run,
    engine: AnalysisEngine,
    timeout: float = 180.0,
) -> OpportunityAnalysis:
    if not run.signals:
        raise AnalysisError("该 Run 没有信号，无法分析。请先采集或手工补录来源。")
    try:
        pack = get_pack(run.domain_pack)
    except KeyError as exc:
        raise AnalysisError(str(exc)) from exc
    try:
        draft = await asyncio.wait_for(engine.draft(run, pack), timeout=timeout)
    except asyncio.TimeoutError as exc:
        raise AnalysisError(f"AI 分析超过 {timeout:.0f} 秒。") from exc
    except AnalysisError:
        raise
    except Exception as exc:
        raise AnalysisError(f"AI 分析失败：{exc}") from exc
    analysis = _finalize(run, pack, draft, engine.name)
    db.save_analysis(run.id, analysis)
    return analysis


def analysis_markdown(run: Run, analysis: OpportunityAnalysis) -> str:
    verdict_label = {"build": "建议投入", "verify": "继续验证", "drop": "放弃"}[
        analysis.verdict
    ]
    lines = [
        f"# 机会判断 · {run.direction}",
        "",
        f"- Run：`{run.id}`",
        f"- 领域包：`{analysis.domain_pack}`",
        f"- 结论：**{verdict_label}**（{analysis.score}/100）",
        f"- 模型：`{analysis.model}`",
        f"- 生成时间：{analysis.created_at}",
        "",
        f"**{analysis.one_liner}**",
        "",
        "## 机会逻辑",
        "",
        analysis.thesis,
        "",
        "## 目标客户",
        "",
        analysis.target_customer,
        "",
        "## 付费意愿",
        "",
        analysis.willingness_to_pay,
        "",
        "## 评分卡",
        "",
        "| 维度 | 分数 | 权重 | 加权分 | 理由 |",
        "|---|---:|---:|---:|---|",
    ]
    for dimension in analysis.dimension_scores:
        lines.append(
            f"| {dimension.name} | {dimension.score}/10 | "
            f"{dimension.weight:.0%} | {dimension.weighted_points} | "
            f"{dimension.rationale.replace('|', '／')} |"
        )
    if analysis.next_actions:
        lines.extend(["", "## 下一步动作", ""])
        for action in analysis.next_actions:
            lines.append(f"- [ ] {action.action}")
    if analysis.risks:
        lines.extend(["", "## 风险", ""])
        lines.extend(f"- {risk}" for risk in analysis.risks)
    if analysis.missing_information:
        lines.extend(["", "## 缺失信息", ""])
        lines.extend(f"- {item}" for item in analysis.missing_information)
    lines.extend(["", "## 引用来源", ""])
    if not analysis.citations:
        lines.append("没有可核对的引用。")
    for citation in analysis.citations:
        lines.append(f"- [{citation.signal_id}]({citation.source_url})")
        if citation.quote:
            lines.append(f"  > {citation.quote}")
    lines.extend(
        [
            "",
            "---",
            "",
            "本判断只基于本次采集的公开信号，不保证站内全量，也不替代真实用户访谈。",
            "",
        ]
    )
    return "\n".join(lines)
