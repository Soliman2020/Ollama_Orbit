# app/main.py

import asyncio
import sys
from contextlib import asynccontextmanager
from typing import Dict, List, Optional

# ── Windows fix ───────────────────────────────────────────────────────────────
# On Windows, explicitly set ProactorEventLoop BEFORE anything else.
# This is required for Playwright's asyncio.create_subprocess_exec to work
# when running inside uvicorn (especially with --reload).
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
# ─────────────────────────────────────────────────────────────────────────────

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import history
from .collector import collect_usage, ensure_states_for_all_accounts
from .config import REFRESH_MINUTES

# ---------------------------------------------------------------------------
# In-memory cache
# ---------------------------------------------------------------------------

usage_cache: List[Dict] = []
last_error: Optional[str] = None
DB_PATH = "data/orbit.db"
history.init_db(DB_PATH)


# ---------------------------------------------------------------------------
# Async refresh
# ---------------------------------------------------------------------------


async def refresh_usage() -> None:
    """
    Run the Playwright collector and update the in-memory cache.
    Called once on startup and on every scheduler tick.
    """
    global usage_cache, last_error
    try:
        data = await collect_usage()
        usage_cache = data
        last_error = None
        # Persist a snapshot for the analytics dashboard. Failures here
        # must not break the scheduler, so swallow + log.
        try:
            await asyncio.to_thread(history.record_snapshot, DB_PATH, data)
        except Exception as exc:
            print(f"[history] record failed: {exc}")
    except Exception as exc:
        last_error = str(exc)
        print(f"[error] refresh_usage failed: {exc}")


# ---------------------------------------------------------------------------
# Lifespan: startup + shutdown
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure all accounts have valid storage_state files.
    await ensure_states_for_all_accounts()

    # Run initial collection so /usage has data immediately.
    await refresh_usage()

    # AsyncIOScheduler runs inside FastAPI's event loop — no thread conflict.
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        refresh_usage,
        "interval",
        minutes=REFRESH_MINUTES,
        id="ollama_usage_refresh",
        replace_existing=True,
    )
    scheduler.start()

    try:
        yield
    finally:
        scheduler.shutdown(wait=False)


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Ollama Usage Monitor",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:3000", "http://localhost:3000"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/usage")
async def get_usage():
    """Return the latest usage snapshot for all accounts."""
    return {"accounts": usage_cache, "error": last_error}


@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "ok", "accounts": len(usage_cache)}


@app.get("/usage/history")
async def usage_history(days: int = 7):
    """Return historical snapshots for the analytics dashboard.

    Capped at 90 days to bound payload size; minimum 1.
    """
    days = max(1, min(days, 90))
    return await asyncio.to_thread(history.read_history, DB_PATH, days)
