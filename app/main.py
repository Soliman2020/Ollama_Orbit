import asyncio
from contextlib import asynccontextmanager
from typing import Dict, List, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .collector import collect_usage, ensure_states_for_all_accounts
from .config import REFRESH_MINUTES

usage_cache: List[Dict] = []
last_error: Optional[str] = None

scheduler = BackgroundScheduler()


async def refresh_usage() -> None:
    """
    Run the collector and update the in-memory cache.
    """
    global usage_cache, last_error
    try:
        data = await collect_usage()
        usage_cache = data
        last_error = None
    except Exception as exc:  # pragma: no cover
        last_error = str(exc)


def scheduler_job() -> None:  # pragma: no cover
    """
    Bridge function for APScheduler (sync) to call the async refresh.
    """
    asyncio.run(refresh_usage())


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan context:
    - Before yield: prepare sessions, start scheduler, run initial refresh.
    - After yield: stop scheduler and cleanup.
    """
    # Ensure all accounts have valid storage_state files (login if needed).
    await ensure_states_for_all_accounts()

    # Run an initial refresh so /usage has data immediately.
    await refresh_usage()

    # Start scheduler for recurring refreshes.
    scheduler.add_job(
        scheduler_job,
        "interval",
        minutes=REFRESH_MINUTES,
        id="ollama_usage_refresh",
        replace_existing=True,
    )
    scheduler.start()

    # Hand control to FastAPI (serve requests).
    try:
        yield
    finally:
        # Shutdown scheduler on app shutdown.
        scheduler.shutdown(wait=False)


app = FastAPI(
    title="Ollama Usage Monitor",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten if exposing publicly
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/usage")
async def get_usage():
    """
    Return the latest usage snapshot for all accounts.
    """
    return {"accounts": usage_cache, "error": last_error}


@app.get("/")
async def root():
    """
    Simple health endpoint.
    """
    return {"status": "ok", "accounts": len(usage_cache)}
