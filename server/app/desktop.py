"""Desktop launcher for Opportunity Scout.

Starts the local FastAPI server, serves the built React web app from the same
origin, and opens the default browser. Used by the packaged macOS app, but
also runnable from a development checkout:

    python3 -m app.desktop
"""

from __future__ import annotations

import argparse
import logging
import os
import secrets
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from logging.handlers import RotatingFileHandler
from pathlib import Path

APP_NAME = "Opportunity Scout"
VERSION = "0.1.0"
DEFAULT_PORT = 8765
PORT_ATTEMPTS = 12

ENV_TEMPLATE = """# Opportunity Scout 本地配置
# 复制为 .env 后按需修改。所有值只保存在本机。
#
# AI（任选一种，未配置时只采集证据、不生成结论）
# OPPORTUNITY_AI_MODEL=gpt-4.1-mini
# OPENAI_API_KEY=sk-...
# OPPORTUNITY_AI_BASE_URL=https://api.deepseek.com/v1
# OPPORTUNITY_AI_API_KEY=...
# OPPORTUNITY_AI_MODEL=ollama:qwen2.5:14b
# OPPORTUNITY_AI_MODEL=anthropic:claude-sonnet-4-5
# ANTHROPIC_API_KEY=sk-ant-...

# RSS / Atom 订阅源，逗号分隔
# OPPORTUNITY_RSS_FEEDS=https://feeds.arstechnica.com/arstechnica/index,https://techcrunch.com/feed/

# Google Trends 地区（默认 US）
# OPPORTUNITY_TRENDS_GEO=US

# Amazon Creators API
# OPPORTUNITY_AMAZON_CREDENTIAL_ID=...
# OPPORTUNITY_AMAZON_CREDENTIAL_SECRET=...
# OPPORTUNITY_AMAZON_TAG=yourtag-20
# OPPORTUNITY_AMAZON_COUNTRY=US

# Agent-Reach 可执行文件（默认从 PATH 查找）
# AGENT_REACH_BIN=/Users/you/.local/bin/agent-reach
# AGENT_REACH_CHANNELS=reddit,web
"""


def data_dir() -> Path:
    override = os.environ.get("OPPORTUNITY_DATA_DIR")
    if override:
        return Path(override).expanduser()
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "OpportunityScout"
    if os.name == "nt":
        return Path(os.environ.get("APPDATA") or Path.home()) / "OpportunityScout"
    return Path(
        os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share"
    ) / "OpportunityScout"


def load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def prepare_environment() -> Path:
    directory = data_dir()
    directory.mkdir(parents=True, exist_ok=True)

    env_file = directory / ".env"
    template = directory / "env.example"
    if not env_file.exists() and not template.exists():
        template.write_text(ENV_TEMPLATE, encoding="utf-8")
    load_env_file(env_file)

    os.environ.setdefault(
        "OPPORTUNITY_SCOUT_DB", str(directory / "opportunity_scout.db")
    )

    # A double-clicked .app does not inherit the shell PATH; add the usual
    # locations so the optional agent-reach CLI can still be found.
    path_parts = os.environ.get("PATH", "").split(os.pathsep)
    for candidate in ("~/.local/bin", "/opt/homebrew/bin", "/usr/local/bin"):
        expanded = str(Path(candidate).expanduser())
        if expanded not in path_parts:
            path_parts.append(expanded)
    os.environ["PATH"] = os.pathsep.join(part for part in path_parts if part)
    return directory


def setup_logging(directory: Path) -> Path:
    log_path = directory / "opportunity_scout.log"
    handlers: list[logging.Handler] = [
        RotatingFileHandler(
            log_path, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
    ]
    if sys.stdout is not None and sys.stdout.isatty():
        handlers.append(logging.StreamHandler(sys.stdout))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
        force=True,
    )
    return log_path


def is_our_instance(port: int) -> bool:
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/api/v1/health", timeout=1
        ) as response:
            body = response.read().decode("utf-8", "replace")
        return "opportunity-scout-api" in body
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def port_is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def choose_port(preferred: int) -> tuple[int, bool]:
    """Return (port, already_running)."""
    if port_is_free(preferred):
        return preferred, False
    if is_our_instance(preferred):
        return preferred, True
    for offset in range(1, PORT_ATTEMPTS + 1):
        candidate = preferred + offset
        if port_is_free(candidate):
            return candidate, False
    raise RuntimeError(f"找不到可用端口：{preferred}–{preferred + PORT_ATTEMPTS}")


def open_when_ready(server, url: str, enabled: bool) -> None:
    for _ in range(200):
        if getattr(server, "started", False):
            if enabled:
                webbrowser.open(url)
            return
        if getattr(server, "should_exit", False):
            return
        time.sleep(0.1)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--port", type=int, default=int(os.environ.get("API_PORT", DEFAULT_PORT)))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)

    directory = prepare_environment()
    log_path = setup_logging(directory)
    log = logging.getLogger("opportunity_scout.desktop")

    # Import after the environment (including .env) is ready: module-level
    # Settings() reads environment variables.
    import uvicorn
    from fastapi import Header, HTTPException

    from app.main import create_app
    from app.config import Settings

    try:
        port, already_running = choose_port(args.port)
    except RuntimeError as exc:
        log.error("%s", exc)
        return 1
    url = f"http://{args.host}:{port}/"
    if already_running:
        log.info("已有实例在运行：%s", url)
        if not args.no_browser:
            webbrowser.open(url)
        return 0

    settings = Settings()
    app = create_app(
        settings,
        cors_origins=[
            f"http://{args.host}:{port}",
            f"http://localhost:{port}",
        ],
    )
    app.state.desktop = True
    token = secrets.token_urlsafe(24)
    app.state.desktop_token = token

    config = uvicorn.Config(
        app,
        host=args.host,
        port=port,
        log_level="info",
        access_log=False,
    )
    server = uvicorn.Server(config)

    @app.post("/api/v1/app/shutdown", tags=["meta"])
    async def shutdown(x_opportunity_token: str | None = Header(default=None)) -> dict:
        if not x_opportunity_token or not secrets.compare_digest(
            x_opportunity_token, token
        ):
            raise HTTPException(status_code=403, detail="无效的退出令牌")
        server.should_exit = True
        return {"ok": True}

    log.info("%s %s 启动：%s", APP_NAME, VERSION, url)
    log.info("数据目录：%s", directory)
    log.info("日志文件：%s", log_path)
    threading.Thread(
        target=open_when_ready,
        args=(server, url, not args.no_browser),
        daemon=True,
    ).start()
    try:
        server.run()
    except KeyboardInterrupt:
        pass
    log.info("已退出")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
