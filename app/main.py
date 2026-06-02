import asyncio
from typing import Dict, List, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .collector import collect_usage, ensure_states_for_all_accounts
from .config import REFRESH_MINUTES

app = FastAPI(title="Ollama Usage Monitor")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For local use; tighten if exposing publicly
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

usage_cache: List[Dict] = []
last_error: Optional[str] = None


async def refresh_usage():
    global usage_cache, last_error
    try:
        data = await collect_usage()
        usage_cache = data
        last_error = None
    except Exception as exc:  # pragma: no cover
        last_error = str(exc)


def scheduler_job():  # pragma: no cover
    asyncio.run(refresh_usage())


scheduler = BackgroundScheduler()
scheduler.add_job(scheduler_job, "interval", minutes=REFRESH_MINUTES)
scheduler.start()


@app.on_event("startup")
async def startup_event():
    await ensure_states_for_all_accounts()
    await refresh_usage()


@app.get("/usage")
async def get_usage():
    return {"accounts": usage_cache, "error": last_error}


@app.get("/")
async def root():
    return {"status": "ok", "accounts": len(usage_cache)}
