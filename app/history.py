"""SQLite persistence for Ollama-Orbit usage snapshots.

Stdlib only — no SQLAlchemy, no Alembic. ponytail: open a fresh
connection per call (no pooling); fine for ~6 accounts × 2 min.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  account TEXT NOT NULL,
  plan TEXT,
  session_percent REAL,
  weekly_percent REAL,
  session_reset TEXT,
  weekly_reset TEXT,
  notes TEXT
);
CREATE INDEX IF NOT EXISTS idx_snapshots_ts ON snapshots(ts);
CREATE INDEX IF NOT EXISTS idx_snapshots_account ON snapshots(account);

CREATE TABLE IF NOT EXISTS model_requests (
  snapshot_id INTEGER NOT NULL,
  model TEXT NOT NULL,
  bucket TEXT NOT NULL,
  requests INTEGER NOT NULL,
  FOREIGN KEY (snapshot_id) REFERENCES snapshots(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_model_requests_snap ON model_requests(snapshot_id);
"""


def init_db(path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.executescript(SCHEMA)
        conn.commit()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def record_snapshot(path: str, accounts: list[dict]) -> None:
    if not accounts:
        return
    ts = _now_iso()
    with sqlite3.connect(path) as conn:
        cur = conn.cursor()
        for acc in accounts:
            cur.execute(
                """
                INSERT INTO snapshots
                  (ts, account, plan, session_percent, weekly_percent,
                   session_reset, weekly_reset, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ts,
                    acc.get("name", "Unknown"),
                    acc.get("plan"),
                    acc.get("sessionPercent"),
                    acc.get("weeklyPercent"),
                    acc.get("sessionReset"),
                    acc.get("weeklyReset"),
                    acc.get("notes", ""),
                ),
            )
            snap_id = cur.lastrowid
            rows: list[tuple[Any, ...]] = []
            for m in acc.get("sessionModels") or []:
                rows.append((snap_id, m.get("model", "Unknown"), "session",
                             int(m.get("requests", 0) or 0)))
            for m in acc.get("weeklyModels") or []:
                rows.append((snap_id, m.get("model", "Unknown"), "weekly",
                             int(m.get("requests", 0) or 0)))
            if rows:
                cur.executemany(
                    "INSERT INTO model_requests (snapshot_id, model, bucket, requests) "
                    "VALUES (?, ?, ?, ?)",
                    rows,
                )
        conn.commit()


def read_history(path: str, days: int) -> dict:
    cutoff = (
        datetime.now(timezone.utc) - timedelta(days=days)
    ).isoformat(timespec="seconds")
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        snap_rows = conn.execute(
            "SELECT id, ts, account, plan, session_percent, weekly_percent, "
            "session_reset, weekly_reset, notes "
            "FROM snapshots WHERE ts >= ? ORDER BY ts ASC",
            (cutoff,),
        ).fetchall()
        snap_ids = [r["id"] for r in snap_rows]
        model_rows: list[sqlite3.Row] = []
        if snap_ids:
            placeholders = ",".join("?" * len(snap_ids))
            model_rows = conn.execute(
                f"SELECT snapshot_id, model, bucket, requests "
                f"FROM model_requests WHERE snapshot_id IN ({placeholders})",
                snap_ids,
            ).fetchall()
        # Build a ts+account lookup so models inherit them client-side.
        snap_meta = {r["id"]: (r["ts"], r["account"]) for r in snap_rows}
    snapshots = [
        {
            "ts": r["ts"],
            "account": r["account"],
            "plan": r["plan"],
            "sessionPercent": r["session_percent"],
            "weeklyPercent": r["weekly_percent"],
            "sessionReset": r["session_reset"],
            "weeklyReset": r["weekly_reset"],
            "notes": r["notes"],
        }
        for r in snap_rows
    ]
    models = [
        {
            "ts": snap_meta[r["snapshot_id"]][0],
            "account": snap_meta[r["snapshot_id"]][1],
            "model": r["model"],
            "bucket": r["bucket"],
            "requests": r["requests"],
        }
        for r in model_rows
    ]
    return {"snapshots": snapshots, "models": models}
