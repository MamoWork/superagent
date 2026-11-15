from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil

from app.providers.base import ProviderError, SourceProvider
from app.schemas import ProviderHealth, ProviderInfo, SearchQuery, Signal

ERROR_MAP: dict[str, str] = {
    "NEED_SETUP": "PROVIDER_NOT_CONFIGURED",
    "NEED_LOGIN": "PROVIDER_NEEDS_AUTH",
    "RATE_LIMITED": "PROVIDER_RATE_LIMITED",
    "PLATFORM_BLOCKED": "PROVIDER_BLOCKED",
    "TIMEOUT": "PROVIDER_TIMEOUT",
    "BUSY": "PROVIDER_BUSY",
    "UPSTREAM_BROKEN": "PROVIDER_UNAVAILABLE",
    "NOT_FOUND": "PROVIDER_NOT_FOUND",
    "BAD_INPUT": "PROVIDER_BAD_REQUEST",
}

CHANNEL_NAMES: dict[str, str] = {
    "reddit": "Reddit",
    "web": "Web Search",
    "github": "GitHub",
    "youtube": "YouTube",
    "twitter": "Twitter / X",
    "facebook": "Facebook",
    "instagram": "Instagram",
    "bilibili": "Bilibili",
    "xiaohongshu": "小红书",
    "linkedin": "LinkedIn",
    "boss": "Boss 直聘",
    "v2ex": "V2EX",
    "xueqiu": "雪球",
    "xiaoyuzhou": "小宇宙",
}

CHANNEL_GROUPS: dict[str, str] = {
    "reddit": "community",
    "v2ex": "community",
    "web": "search",
    "github": "developer",
    "youtube": "content",
    "bilibili": "content",
    "xiaoyuzhou": "content",
    "twitter": "social",
    "facebook": "social",
    "instagram": "social",
    "xiaohongshu": "social",
    "linkedin": "professional",
    "boss": "jobs",
    "xueqiu": "finance",
}

# Only the Reddit channel needs an explicit public-web backend here. The web
# channel has its own backend choice (exa) and rejects --backend public-web.
CHANNEL_BACKENDS: dict[str, str] = {"reddit": "public-web"}

CHANNEL_AUTH: dict[str, str] = {
    "twitter": "browser",
    "facebook": "browser",
    "instagram": "browser",
    "bilibili": "browser",
    "xiaohongshu": "browser",
    "linkedin": "browser",
    "boss": "browser",
    "xueqiu": "browser",
}


class AgentReachProvider(SourceProvider):
    """Adapter around the Agent-Reach CLI.

    This is the only class that knows the CLI syntax, output schema and error
    codes. If Agent-Reach later becomes an HTTP or MCP service, replace this
    class and leave the rest of the application unchanged.
    """

    def __init__(
        self,
        channel: str,
        name: str | None = None,
        bin_path: str = "agent-reach",
        backend: str | None = None,
        timeout: float = 90.0,
    ) -> None:
        self.channel = channel
        self.bin_path = bin_path
        self.backend = backend if backend is not None else CHANNEL_BACKENDS.get(channel)
        self.timeout = timeout
        self._semaphore = asyncio.Semaphore(2)
        self.info = ProviderInfo(
            id=f"agent-reach.{channel}",
            name=name or CHANNEL_NAMES.get(channel, channel.title()),
            group=CHANNEL_GROUPS.get(channel, "other"),
            capabilities=["search"],
            auth=CHANNEL_AUTH.get(channel, "none"),
            status="ready",
            cost="free",
            rate_limit={"requests": 10, "window_seconds": 60},
            note="通过 Agent-Reach 适配器采集公开内容；结果不保证站内全量。",
        )

    def _resolve_bin(self) -> str | None:
        if os.path.isabs(self.bin_path):
            return self.bin_path if os.path.exists(self.bin_path) else None
        return shutil.which(self.bin_path)

    async def health(self) -> ProviderHealth:
        resolved = self._resolve_bin()
        if resolved:
            return ProviderHealth(id=self.info.id, status="ready", detail=resolved)
        return ProviderHealth(
            id=self.info.id,
            status="not_configured",
            detail=f"未找到 Agent-Reach 可执行文件：{self.bin_path}",
        )

    async def search(self, query: SearchQuery) -> list[Signal]:
        if not self._resolve_bin():
            raise ProviderError(
                "PROVIDER_NOT_CONFIGURED",
                f"未找到 Agent-Reach 可执行文件：{self.bin_path}",
                "请先安装 Agent-Reach，或通过 AGENT_REACH_BIN 指定路径。",
            )

        cmd = [
            self.bin_path,
            self.channel,
            "search",
            query.text,
            "--limit",
            str(query.limit),
        ]
        backend = query.backend or self.backend
        if backend:
            cmd.extend(["--backend", backend])

        async with self._semaphore:
            stdout, stderr = await self._exec(cmd)

        payload = self._parse(stdout, stderr)
        if not payload.get("ok", False):
            raise self._to_error(payload)

        signals: list[Signal] = []
        for item in payload.get("items") or []:
            if isinstance(item, dict) and item.get("url"):
                signals.append(self._normalize(item))
        return signals

    async def _exec(self, cmd: list[str]) -> tuple[str, str]:
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise ProviderError(
                "PROVIDER_NOT_CONFIGURED",
                f"无法启动 Agent-Reach：{exc}",
                "请检查 AGENT_REACH_BIN。",
            ) from exc

        try:
            raw_out, raw_err = await asyncio.wait_for(
                proc.communicate(), timeout=self.timeout
            )
        except asyncio.TimeoutError as exc:
            try:
                proc.kill()
                await proc.wait()
            except ProcessLookupError:
                pass
            raise ProviderError(
                "PROVIDER_TIMEOUT",
                f"Agent-Reach {self.channel} 搜索超过 {self.timeout:.0f} 秒。",
                "稍后重试；不要循环重试或切换账号。",
            ) from exc

        return (
            raw_out.decode("utf-8", errors="replace"),
            raw_err.decode("utf-8", errors="replace"),
        )

    def _parse(self, stdout: str, stderr: str) -> dict:
        text = stdout.strip()
        if not text:
            raise ProviderError(
                "PROVIDER_BAD_OUTPUT",
                f"Agent-Reach 没有返回内容。stderr: {stderr[:400]}",
            )
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ProviderError(
                "PROVIDER_BAD_OUTPUT",
                f"Agent-Reach 返回的不是 JSON：{text[:400]}",
                f"stderr: {stderr[:400]}",
            ) from exc
        if not isinstance(payload, dict):
            raise ProviderError("PROVIDER_BAD_OUTPUT", "Agent-Reach 返回值不是对象。")
        return payload

    def _to_error(self, payload: dict) -> ProviderError:
        raw = payload.get("error") or {}
        platform_code = str(raw.get("code") or "UNKNOWN")
        code = ERROR_MAP.get(platform_code, "PROVIDER_ERROR")
        retry_after = raw.get("retry_after_seconds")
        try:
            retry_after = int(retry_after) if retry_after is not None else None
        except (TypeError, ValueError):
            retry_after = None
        return ProviderError(
            code=code,
            message=str(raw.get("message") or "Agent-Reach 调用失败。"),
            hint=str(raw.get("hint") or ""),
            retry_after_seconds=retry_after,
        )

    def _normalize(self, item: dict) -> Signal:
        url = str(item.get("url") or "")
        title = str(item.get("title") or "")
        raw = item.get("raw") if isinstance(item.get("raw"), dict) else None
        metrics = item.get("metrics") if isinstance(item.get("metrics"), dict) else {}
        signal_id = hashlib.sha256(
            f"{self.info.id}|{url}|{title}".encode("utf-8")
        ).hexdigest()[:24]
        return Signal(
            id=signal_id,
            provider_id=self.info.id,
            source_type="post" if self.channel == "reddit" else "web",
            source_url=url,
            title=title,
            quote=str(item.get("text") or ""),
            author_public=item.get("author"),
            published_at=item.get("published_at"),
            metrics=metrics,
            raw=raw,
        )
