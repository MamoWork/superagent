"""Print the API OpenAPI document without touching real application data.

Used by `npm run gen:api` in the web project. The module-level FastAPI app in
`app.main` creates a database on import, so point it at a temporary directory
before importing it.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER_ROOT))

with tempfile.TemporaryDirectory() as temp_dir:
    temp = Path(temp_dir)
    os.environ["OPPORTUNITY_SCOUT_DB"] = str(temp / "import.db")
    os.environ["OPPORTUNITY_WEB_DIST"] = str(temp / "missing-web")
    os.environ["OPPORTUNITY_SCHEDULER_ENABLED"] = "0"

    from app.config import Settings  # noqa: E402
    from app.main import create_app  # noqa: E402

    application = create_app(
        Settings(
            db_path=temp / "openapi.db",
            web_dist_dir=temp / "missing-web",
            scheduler_enabled=False,
        )
    )
    print(json.dumps(application.openapi(), ensure_ascii=False, indent=2))
