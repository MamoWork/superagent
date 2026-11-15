from __future__ import annotations

import json
from pathlib import Path

WEB_INDEX = "index.html"


def web_dist_candidates(override: Path | None = None) -> list[Path]:
    """Return the possible locations of the built Vite app.

    An explicit override is authoritative (used by tests and custom
    deployments). Otherwise prefer the PyInstaller data directory, then the
    development checkout.
    """
    if override is not None:
        return [Path(override).expanduser()]
    here = Path(__file__).resolve()
    return [
        here.parent / "static" / "web",
        here.parents[2] / "web" / "dist",
    ]


def resolve_web_dist(override: Path | None = None) -> Path | None:
    for candidate in web_dist_candidates(override):
        if (candidate / WEB_INDEX).is_file():
            return candidate
    return None


def read_index_html(dist: Path | None) -> str | None:
    if dist is None:
        return None
    index = dist / WEB_INDEX
    if not index.is_file():
        return None
    return index.read_text(encoding="utf-8")


def assets_dir(dist: Path | None) -> Path | None:
    if dist is None:
        return None
    assets = dist / "assets"
    return assets if assets.is_dir() else None


def inject_runtime_config(
    html: str,
    api_base: str = "/api/v1",
    desktop_token: str | None = None,
) -> str:
    """Inject the API base (and desktop quit token) before </head>."""
    lines = [
        "<script>window.OPPORTUNITY_API_BASE="
        f"{json.dumps(api_base, ensure_ascii=False)};</script>"
    ]
    if desktop_token:
        lines.append(
            "<script>window.OPPORTUNITY_DESKTOP_TOKEN="
            f"{json.dumps(desktop_token, ensure_ascii=False)};</script>"
        )
    tag = "".join(lines)
    lowered = html.lower()
    index = lowered.find("</head>")
    if index == -1:
        return tag + html
    return html[:index] + tag + html[index:]
