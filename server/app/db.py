from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.schemas import OpportunityAnalysis, Signal

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    domain_pack TEXT NOT NULL,
    direction TEXT NOT NULL,
    keywords TEXT NOT NULL DEFAULT '[]',
    provider_ids TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL,
    stats TEXT NOT NULL DEFAULT '{}',
    error TEXT,
    created_at TEXT NOT NULL,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS signals (
    run_id TEXT NOT NULL,
    id TEXT NOT NULL,
    provider_id TEXT NOT NULL,
    source_type TEXT NOT NULL DEFAULT 'post',
    source_url TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    quote TEXT NOT NULL DEFAULT '',
    author_public TEXT,
    published_at TEXT,
    metrics TEXT NOT NULL DEFAULT '{}',
    raw_json TEXT,
    created_at TEXT NOT NULL,
    PRIMARY KEY (run_id, id),
    FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_signals_run ON signals(run_id);
CREATE INDEX IF NOT EXISTS idx_runs_created ON runs(created_at DESC);

CREATE TABLE IF NOT EXISTS analyses (
    run_id TEXT PRIMARY KEY,
    payload TEXT NOT NULL,
    model TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS schedules (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    name TEXT NOT NULL DEFAULT '',
    domain_pack TEXT NOT NULL,
    direction TEXT NOT NULL,
    keywords TEXT NOT NULL DEFAULT '[]',
    provider_ids TEXT NOT NULL DEFAULT '[]',
    limit_per_provider INTEGER NOT NULL DEFAULT 20,
    time_range_days INTEGER,
    cron TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    last_run_id TEXT,
    last_run_at TEXT,
    last_error TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS saved_opportunities (
    run_id TEXT PRIMARY KEY,
    stage TEXT NOT NULL DEFAULT 'saved',
    notes TEXT NOT NULL DEFAULT '',
    verdict TEXT NOT NULL,
    score INTEGER NOT NULL,
    direction TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_saved_stage ON saved_opportunities(stage);
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def init(self) -> None:
        with self._connect() as conn:
            conn.executescript(SCHEMA)
            # Lightweight migration for databases created before schedule names.
            schedule_columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(schedules)").fetchall()
            }
            if "name" not in schedule_columns:
                conn.execute(
                    "ALTER TABLE schedules ADD COLUMN name TEXT NOT NULL DEFAULT ''"
                )

    def create_run(self, run: dict) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO runs (
                    id, workspace_id, domain_pack, direction, keywords,
                    provider_ids, status, stats, error, created_at, finished_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run["id"],
                    run["workspace_id"],
                    run["domain_pack"],
                    run["direction"],
                    json.dumps(run.get("keywords", []), ensure_ascii=False),
                    json.dumps(run.get("provider_ids", []), ensure_ascii=False),
                    run["status"],
                    json.dumps(run.get("stats", {}), ensure_ascii=False),
                    run.get("error"),
                    run["created_at"],
                    run.get("finished_at"),
                ),
            )

    def update_run(self, run_id: str, **fields: object) -> None:
        allowed = {"status", "stats", "error", "finished_at"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return
        if "stats" in updates:
            updates["stats"] = json.dumps(updates["stats"], ensure_ascii=False)
        columns = ", ".join(f"{key} = ?" for key in updates)
        values = list(updates.values()) + [run_id]
        with self._connect() as conn:
            conn.execute(f"UPDATE runs SET {columns} WHERE id = ?", values)

    def add_signals(self, run_id: str, signals: list[Signal]) -> None:
        if not signals:
            return
        now = utcnow()
        rows = [
            (
                run_id,
                signal.id,
                signal.provider_id,
                signal.source_type,
                signal.source_url,
                signal.title,
                signal.quote,
                signal.author_public,
                signal.published_at,
                json.dumps(signal.metrics, ensure_ascii=False),
                json.dumps(signal.raw, ensure_ascii=False) if signal.raw else None,
                now,
            )
            for signal in signals
        ]
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT OR IGNORE INTO signals (
                    run_id, id, provider_id, source_type, source_url, title,
                    quote, author_public, published_at, metrics, raw_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )

    def get_run(self, run_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        return self._row_to_run(row) if row else None

    def list_runs(self, limit: int = 50) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM runs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._row_to_run(row) for row in rows]

    def get_signals(self, run_id: str) -> list[Signal]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM signals WHERE run_id = ? ORDER BY rowid", (run_id,)
            ).fetchall()
        return [self._row_to_signal(row) for row in rows]

    def get_signal(self, run_id: str, signal_id: str) -> Signal | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM signals WHERE run_id = ? AND id = ?",
                (run_id, signal_id),
            ).fetchone()
        return self._row_to_signal(row) if row else None

    def save_analysis(self, run_id: str, analysis: "OpportunityAnalysis") -> None:
        payload = analysis.model_dump(mode="json")
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO analyses (run_id, payload, model, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    payload = excluded.payload,
                    model = excluded.model,
                    created_at = excluded.created_at
                """,
                (
                    run_id,
                    json.dumps(payload, ensure_ascii=False),
                    analysis.model,
                    analysis.created_at,
                ),
            )

    def get_analysis(self, run_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload FROM analyses WHERE run_id = ?", (run_id,)
            ).fetchone()
        return json.loads(row["payload"]) if row else None

    def has_analysis(self, run_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM analyses WHERE run_id = ? LIMIT 1", (run_id,)
            ).fetchone()
        return row is not None

    def run_ids_with_analysis(self, run_ids: list[str]) -> set[str]:
        if not run_ids:
            return set()
        placeholders = ",".join("?" for _ in run_ids)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT run_id FROM analyses WHERE run_id IN ({placeholders})",
                run_ids,
            ).fetchall()
        return {row["run_id"] for row in rows}

    def create_schedule(self, schedule: dict) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO schedules (
                    id, workspace_id, name, domain_pack, direction, keywords,
                    provider_ids, limit_per_provider, time_range_days, cron,
                    enabled, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    schedule["id"],
                    schedule["workspace_id"],
                    schedule.get("name", ""),
                    schedule["domain_pack"],
                    schedule["direction"],
                    json.dumps(schedule.get("keywords", []), ensure_ascii=False),
                    json.dumps(schedule.get("provider_ids", []), ensure_ascii=False),
                    schedule["limit_per_provider"],
                    schedule.get("time_range_days"),
                    schedule["cron"],
                    int(schedule.get("enabled", True)),
                    schedule["created_at"],
                ),
            )

    def list_schedules(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM schedules ORDER BY created_at DESC"
            ).fetchall()
        return [self._row_to_schedule(row) for row in rows]

    def get_schedule(self, schedule_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM schedules WHERE id = ?", (schedule_id,)
            ).fetchone()
        return self._row_to_schedule(row) if row else None

    def update_schedule(self, schedule_id: str, **fields: object) -> None:
        allowed = {
            "name",
            "domain_pack",
            "direction",
            "keywords",
            "provider_ids",
            "limit_per_provider",
            "time_range_days",
            "cron",
            "enabled",
        }
        updates = {key: value for key, value in fields.items() if key in allowed}
        if not updates:
            return
        for key in ("keywords", "provider_ids"):
            if key in updates:
                updates[key] = json.dumps(updates[key], ensure_ascii=False)
        if "enabled" in updates:
            updates["enabled"] = int(bool(updates["enabled"]))
        columns = ", ".join(f"{key} = ?" for key in updates)
        values = list(updates.values()) + [schedule_id]
        with self._connect() as conn:
            conn.execute(f"UPDATE schedules SET {columns} WHERE id = ?", values)

    def delete_schedule(self, schedule_id: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM schedules WHERE id = ?", (schedule_id,)
            )
        return cursor.rowcount > 0

    def mark_schedule_run(
        self,
        schedule_id: str,
        run_id: str,
        error: str | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE schedules
                SET last_run_id = ?, last_run_at = ?, last_error = ?
                WHERE id = ?
                """,
                (run_id, utcnow(), error, schedule_id),
            )

    def upsert_saved_opportunity(
        self,
        run_id: str,
        *,
        stage: str,
        notes: str,
        verdict: str,
        score: int,
        direction: str,
        payload: dict,
        created_at: str,
        updated_at: str,
    ) -> None:
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT created_at FROM saved_opportunities WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            effective_created = existing["created_at"] if existing else created_at
            conn.execute(
                """
                INSERT INTO saved_opportunities (
                    run_id, stage, notes, verdict, score, direction,
                    payload, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    stage = excluded.stage,
                    notes = excluded.notes,
                    verdict = excluded.verdict,
                    score = excluded.score,
                    direction = excluded.direction,
                    payload = excluded.payload,
                    updated_at = excluded.updated_at
                """,
                (
                    run_id,
                    stage,
                    notes,
                    verdict,
                    score,
                    direction,
                    json.dumps(payload, ensure_ascii=False),
                    effective_created,
                    updated_at,
                ),
            )

    def list_saved_opportunities(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM saved_opportunities
                ORDER BY CASE stage
                    WHEN 'saved' THEN 0
                    WHEN 'validating' THEN 1
                    WHEN 'contacted' THEN 2
                    WHEN 'replied' THEN 3
                    WHEN 'won' THEN 4
                    WHEN 'dropped' THEN 5
                    ELSE 6
                END, updated_at DESC
                """
            ).fetchall()
        return [self._row_to_saved_opportunity(row) for row in rows]

    def get_saved_opportunity(self, run_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM saved_opportunities WHERE run_id = ?", (run_id,)
            ).fetchone()
        return self._row_to_saved_opportunity(row) if row else None

    def update_saved_opportunity(self, run_id: str, **fields: object) -> None:
        allowed = {"stage", "notes"}
        updates = {key: value for key, value in fields.items() if key in allowed}
        if not updates:
            return
        updates["updated_at"] = utcnow()
        columns = ", ".join(f"{key} = ?" for key in updates)
        values = list(updates.values()) + [run_id]
        with self._connect() as conn:
            conn.execute(
                f"UPDATE saved_opportunities SET {columns} WHERE run_id = ?", values
            )

    def delete_saved_opportunity(self, run_id: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM saved_opportunities WHERE run_id = ?", (run_id,)
            )
        return cursor.rowcount > 0

    @staticmethod
    def _row_to_saved_opportunity(row: sqlite3.Row) -> dict:
        payload = json.loads(row["payload"])
        payload["stage"] = row["stage"]
        payload["notes"] = row["notes"]
        payload["created_at"] = row["created_at"]
        payload["updated_at"] = row["updated_at"]
        return payload

    @staticmethod
    def _row_to_schedule(row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "workspace_id": row["workspace_id"],
            "name": row["name"] if "name" in row.keys() else "",
            "domain_pack": row["domain_pack"],
            "direction": row["direction"],
            "keywords": json.loads(row["keywords"] or "[]"),
            "provider_ids": json.loads(row["provider_ids"] or "[]"),
            "limit_per_provider": row["limit_per_provider"],
            "time_range_days": row["time_range_days"],
            "cron": row["cron"],
            "enabled": bool(row["enabled"]),
            "last_run_id": row["last_run_id"],
            "last_run_at": row["last_run_at"],
            "last_error": row["last_error"],
            "created_at": row["created_at"],
        }

    @staticmethod
    def _row_to_run(row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "workspace_id": row["workspace_id"],
            "domain_pack": row["domain_pack"],
            "direction": row["direction"],
            "keywords": json.loads(row["keywords"] or "[]"),
            "provider_ids": json.loads(row["provider_ids"] or "[]"),
            "status": row["status"],
            "stats": json.loads(row["stats"] or "{}"),
            "error": row["error"],
            "created_at": row["created_at"],
            "finished_at": row["finished_at"],
        }

    @staticmethod
    def _row_to_signal(row: sqlite3.Row) -> Signal:
        return Signal(
            id=row["id"],
            provider_id=row["provider_id"],
            source_type=row["source_type"],
            source_url=row["source_url"],
            title=row["title"],
            quote=row["quote"],
            author_public=row["author_public"],
            published_at=row["published_at"],
            metrics=json.loads(row["metrics"] or "{}"),
            raw=json.loads(row["raw_json"]) if row["raw_json"] else None,
        )
