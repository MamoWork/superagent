from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from app.config import SERVER_ROOT, Settings
from app.db import Database
from app.domain_packs import list_packs
from app.providers.registry import build_registry
from app.schemas import RunCreate
from app.services.analysis import brief_markdown, build_brief
from app.services.analyzer import (
    AnalysisError,
    analyze_run,
    analysis_markdown,
    build_engine,
)
from app.services.runs import execute_run, get_run_detail


def _cmd_providers(registry) -> None:
    print(f"{'ID':32} {'NAME':18} {'GROUP':12} {'AUTH':8} {'STATUS'}")
    print("-" * 90)
    for provider in registry.list():
        print(
            f"{provider.id:32} {provider.name:18} {provider.group:12} "
            f"{provider.auth:8} {provider.status}"
        )


def _cmd_run(args: argparse.Namespace, settings: Settings) -> None:
    db = Database(settings.db_path)
    db.init()
    registry = build_registry(settings)

    provider_ids = [
        item.strip() for item in args.providers.split(",") if item.strip()
    ] or registry.ids()
    keywords = [item.strip() for item in args.keywords.split(",") if item.strip()]
    payload = RunCreate(
        workspace_id="cli",
        domain_pack=args.pack,
        direction=args.direction,
        keywords=keywords,
        provider_ids=provider_ids,
        limit_per_provider=args.limit,
        time_range_days=args.days,
    )
    run = asyncio.run(execute_run(db, registry, payload))
    brief = build_brief(run)
    markdown = brief_markdown(run, brief)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"{run.id}.json"
    md_path = out_dir / f"{run.id}.md"
    json_path.write_text(run.model_dump_json(indent=2), encoding="utf-8")
    md_path.write_text(markdown, encoding="utf-8")

    print(markdown)
    print(f"\n已保存：{json_path}")
    print(f"已保存：{md_path}")

    if args.analyze:
        _analyze_and_write(args, settings, run, out_dir)


def _analyze_and_write(args, settings: Settings, run, out_dir: Path) -> None:
    engine = build_engine(settings, getattr(args, "model", None))
    if engine is None:
        print(
            "\n未配置 AI 模型，跳过分析。设置 OPPORTUNITY_AI_MODEL 后重试，"
            "或运行 `python -m app.cli analyze --run <id>`。"
        )
        return
    try:
        analysis = asyncio.run(
            analyze_run(
                Database(settings.db_path),
                run,
                engine,
                timeout=settings.ai_timeout + 30,
            )
        )
    except AnalysisError as exc:
        print(f"\nAI 分析失败：{exc}")
        return
    markdown = analysis_markdown(run, analysis)
    analysis_json = out_dir / f"{run.id}.analysis.json"
    analysis_md = out_dir / f"{run.id}.analysis.md"
    analysis_json.write_text(
        analysis.model_dump_json(indent=2), encoding="utf-8"
    )
    analysis_md.write_text(markdown, encoding="utf-8")
    print(markdown)
    print(f"\n已保存：{analysis_json}")
    print(f"已保存：{analysis_md}")


def _cmd_analyze(args: argparse.Namespace, settings: Settings) -> int:
    db = Database(settings.db_path)
    db.init()
    run = get_run_detail(db, args.run)
    if run is None:
        print(f"Run 不存在：{args.run}")
        return 1
    engine = build_engine(settings, args.model)
    if engine is None:
        print(
            "未配置 AI 模型。请设置 OPPORTUNITY_AI_MODEL，"
            "例如 gpt-4.1-mini、deepseek-chat 或 anthropic:claude-sonnet-4-5。"
        )
        return 2
    try:
        analysis = asyncio.run(
            analyze_run(db, run, engine, timeout=settings.ai_timeout + 30)
        )
    except AnalysisError as exc:
        print(f"AI 分析失败：{exc}")
        return 3
    markdown = analysis_markdown(run, analysis)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"{run.id}.analysis.json"
    md_path = out_dir / f"{run.id}.analysis.md"
    json_path.write_text(analysis.model_dump_json(indent=2), encoding="utf-8")
    md_path.write_text(markdown, encoding="utf-8")
    print(markdown)
    print(f"\n已保存：{json_path}")
    print(f"已保存：{md_path}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="opportunity-scout",
        description="Local-first opportunity research CLI (concierge mode).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("providers", help="List configured data source adapters.")
    sub.add_parser("packs", help="List domain packs and their scorecards.")

    run_parser = sub.add_parser(
        "run",
        help="Run one collection and write a Markdown evidence brief.",
    )
    run_parser.add_argument(
        "--direction",
        required=True,
        help="研究方向的自然语言描述，例如：Amazon 宠物饮水机细分机会。",
    )
    run_parser.add_argument(
        "--keywords",
        default="",
        help="逗号分隔的补充关键词。",
    )
    run_parser.add_argument(
        "--providers",
        default="",
        help="逗号分隔的 provider id；默认使用全部已配置数据源。",
    )
    run_parser.add_argument(
        "--pack",
        default="crossborder",
        help="领域包 id，例如 crossborder、saas。",
    )
    run_parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="每个数据源最多采集条数。",
    )
    run_parser.add_argument(
        "--days",
        type=int,
        default=90,
        help="时间范围（天）。",
    )
    run_parser.add_argument(
        "--out",
        default=str(SERVER_ROOT / "briefs"),
        help="brief 输出目录。",
    )
    run_parser.add_argument(
        "--analyze",
        action="store_true",
        help="采集完成后立即调用已配置的 AI 引擎生成机会判断。",
    )
    run_parser.add_argument(
        "--model",
        default=None,
        help="覆盖 OPPORTUNITY_AI_MODEL，仅与 --analyze 一起使用。",
    )

    analyze_parser = sub.add_parser(
        "analyze",
        help="对已有 Run 调用 AI 引擎，生成机会判断。",
    )
    analyze_parser.add_argument(
        "--run",
        required=True,
        help="Run id，例如 run_98bac940d660。",
    )
    analyze_parser.add_argument(
        "--model",
        default=None,
        help="覆盖 OPPORTUNITY_AI_MODEL。",
    )
    analyze_parser.add_argument(
        "--out",
        default=str(SERVER_ROOT / "briefs"),
        help="分析结果输出目录。",
    )

    args = parser.parse_args()
    settings = Settings()

    if args.command == "providers":
        _cmd_providers(build_registry(settings))
        return
    if args.command == "packs":
        for pack in list_packs():
            print(f"{pack.id:14} {pack.name:14} {pack.output_schema}")
            for dimension in pack.scorecard:
                print(
                    f"  - {dimension.name:8} {dimension.weight:.0%}  "
                    f"{dimension.description}"
                )
        return
    if args.command == "run":
        _cmd_run(args, settings)
        return
    if args.command == "analyze":
        raise SystemExit(_cmd_analyze(args, settings))
    parser.error("未知命令")


if __name__ == "__main__":
    main()
