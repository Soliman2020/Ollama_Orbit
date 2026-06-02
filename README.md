# Ollama Usage Monitor

A self-hosted dashboard that tracks session and weekly usage across **multiple Ollama Cloud accounts** in one place — so you never have to log into each account manually at https://ollama.com/settings.

The backend scrapes the Usage page for every configured account using Playwright (saved browser sessions), caches the results, and exposes them through a FastAPI API. The frontend is a single HTML file that reads from that API and displays everything in a clean auto-refreshing dashboard.

---

## Table of Contents

1. [Project Structure](#project-structure)
2. [How It Works](#how-it-works)
3. [Prerequisites](#prerequisites)
4. [Installation](#installation)
5. [Configuration](#configuration)
6. [First-Time Login (Save Sessions)](#first-time-login-save-sessions)
7. [Running the Backend](#running-the-backend)
8. [Running the Frontend](#running-the-frontend)
9. [API Reference](#api-reference)
10. [Data Model](#data-model)
11. [Fixing the Frontend ↔ Backend Connection (CORS)](#fixing-the-frontend--backend-connection-cors)
12. [Security Notes](#security-notes)
13. [Adapting to Ollama UI Changes](#adapting-to-ollama-ui-changes)
14. [Quick-Start Summary](#quick-start-summary)

---

## Project Structure

```
ollama_dashboard/
├── app/
│   ├── __init__.py          # Package marker
│   ├── config.py            # All configuration: accounts, refresh interval, URLs
│   ├── collector.py         # Playwright scraper + login helper CLI
│   └── main.py              # FastAPI app, scheduler, API endpoints
├── frontend/
│   └── dashboard.html       # Single-file HTML/CSS/JS dashboard
├── sessions/                # Playwright storage-state files (one per account)
│   ├── state_account1.json
│   ├── state_account2.json
│   └── ...                  # Created automatically after first login
├── requirements.txt         # Python dependencies
└── README.md
```

> **Important:** The `sessions/` folder contains authenticated browser sessions.
> Treat every file inside it as a secret — do not commit them to any public repository.

---

## How It Works

```
┌──────────────────────────────────────────────────────────────┐
│                        BACKEND                               │
│                                                              │
│  APScheduler (every N minutes)                               │
│       │                                                      │
│       ▼                                                      │
│  collector.py ──► Playwright (headless browser)              │
│       │               │                                      │
│       │         Loads sessions/state_accountX.json           │
│       │               │                                      │
│       │         Opens https://ollama.com/settings            │
│       │               │                                      │
│       │         Parses: session %, weekly %, resets,         │
│       │                 model usage lines                     │
│       │                                                      │
│       ▼                                                      │
│  usage_cache (in-memory list of account objects)             │
│       │                                                      │
│  FastAPI ──► GET /usage  ──► returns JSON cache              │
│         └──► GET /       ──► health check                    │
└──────────────────────────────────────────────────────────────┘
                          │  HTTP fetch (every 5 min)
                          ▼
┌──────────────────────────────────────────────────────────────┐
│                       FRONTEND                               │
│                                                              │
│  frontend/dashboard.html                                     │
│  ├── KPI cards: total accounts, avg/highest weekly usage,    │
│  │              critical (>80%), idle (0%)                   │
│  ├── Cards View: per-account session/weekly bars + resets    │
│  └── Table View: side-by-side comparison across accounts     │
└──────────────────────────────────────────────────────────────┘
```

---

## Prerequisites

- **Python 3.10+**
- **pip**
- Ollama Cloud accounts with access to the Usage page at https://ollama.com/settings
- Basic command-line familiarity

---

## Installation

### 1. Clone / Download the project

```bash
git clone <your-repo-url> ollama_dashboard
cd ollama_dashboard
```

### 2. Create and activate a virtual environment (recommended)

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

### 3. Install Python dependencies

```bash
pip install -r requirements.txt
```

`requirements.txt` includes:
- `fastapi` — the API framework
- `uvicorn` — the ASGI server that runs FastAPI
- `playwright` — headless browser automation for scraping
- `apscheduler` — background job scheduler
- `python-dotenv` *(optional)* — for loading secrets from a `.env` file

### 4. Install Playwright browsers

```bash
playwright install chromium
```

---

## Configuration

All settings live in `app/config.py`. Open it and edit the following:

```python
# app/config.py

ACCOUNTS = [
    {
        "name": "Account_1",          # Label shown in the dashboard
        "plan": "Free",               # Plan label (Free / Developer / Pro)
        "email": "you@example.com",   # Ollama login email
        "password": "secret123",      # Password — or use os.getenv("OLLAMA_PWD_1")
        "storage": "sessions/state_account1.json",  # Session file path
        "notes": "",                  # Optional internal note
    },
    # ... repeat for each account
]

REFRESH_MINUTES = 5          # How often the scheduler re-scrapes all accounts
SETTINGS_URL = "https://ollama.com/settings"  # Change only if Ollama moves this page
```

**Tip — use environment variables instead of hardcoded passwords:**

```python
import os
"password": os.getenv("OLLAMA_PWD_1", "fallback-only-for-dev"),
```

Then create a `.env` file (never commit it):

```
OLLAMA_PWD_1=mypassword1
OLLAMA_PWD_2=mypassword2
```

---

## First-Time Login (Save Sessions)

Playwright needs one authenticated browser session per account before it can run headlessly.
Do this **once per account**:

```bash
# From the project root with your venv active:
python -m app.collector --login
```

This will open a visible browser window for each account, log in using the credentials in `config.py`,
and save a `state_accountX.json` file into the `sessions/` folder.

After this step, Playwright will reuse those saved sessions — no more interactive logins are needed.

> If a session expires, re-run `--login` for that account only.

---

## Running the Backend

```bash
# From the project root:
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

On startup the backend will:
1. Trigger an immediate usage collection for all accounts.
2. Start the APScheduler job that re-collects every `REFRESH_MINUTES`.
3. Serve the API at `http://127.0.0.1:8000`.

**Verify it is running:**

| URL | Expected response |
|-----|-------------------|
| http://127.0.0.1:8000/ | `{"status":"ok","accounts":6}` |
| http://127.0.0.1:8000/usage | JSON array of all account objects |
| http://127.0.0.1:8000/docs | Swagger UI — interactive API documentation |

---

## Running the Frontend

> **Do NOT open `dashboard.html` by double-clicking it.**
> Opening it as a `file://` URL causes CORS errors — the browser blocks the fetch to the backend.
> See [Fixing the Frontend ↔ Backend Connection (CORS)](#fixing-the-frontend--backend-connection-cors) below.

### Correct way — serve it via a local HTTP server

Open a **second terminal** (keep the backend running in the first):

```bash
cd C:\Users\msoli\Desktop\ollama_dashboard\frontend
python -m http.server 3000
```

Then open your browser and go to:

```
http://127.0.0.1:3000/dashboard.html
```

The dashboard will connect to the backend at `http://127.0.0.1:8000/usage` and display all account data.
It auto-refreshes every 5 minutes.

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Health check — returns `{"status":"ok","accounts":N}` |
| GET | `/usage` | Returns latest scraped usage for all accounts |

**Interactive docs:** http://127.0.0.1:8000/docs (Swagger UI, version 0.1.0)

---

## Data Model

Each account object returned by `GET /usage` looks like this:

```json
{
  "name": "Account_1",
  "plan": "Free",
  "sessionPercent": 0,
  "weeklyPercent": 38,
  "sessionReset": "2 hours.",
  "weeklyReset": "5 days.",
  "notes": ""
}
```

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Account label from `config.py` |
| `plan` | string | Plan tier (Free / Developer / Pro) |
| `sessionPercent` | number | Session usage % from the Ollama Usage page |
| `weeklyPercent` | number | Weekly usage % from the Ollama Usage page |
| `sessionReset` | string | Time until session resets, e.g. `"2 hours."` |
| `weeklyReset` | string | Time until weekly resets, e.g. `"5 days."` |
| `notes` | string | Optional internal label set in `config.py` |

The full response envelope is:

```json
{
  "accounts": [ "...array of account objects..." ],
  "error": null
}
```

---

## Fixing the Frontend ↔ Backend Connection (CORS)

If you open `dashboard.html` directly from the file system (`file:///...`), the browser treats it as a
**null origin** and blocks all `fetch()` calls to the backend — this is a browser CORS security rule,
not a bug in the code.

**You will see:** the dashboard stays on "Connecting…" with dashes for all values.

### Fix A — Serve the frontend via HTTP (simplest, recommended)

```bash
cd frontend
python -m http.server 3000
# Then open: http://127.0.0.1:3000/dashboard.html
```

### Fix B — Add CORS headers to the backend

Add this to `app/main.py` right after `app = FastAPI(...)`:

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # or ["null"] to be more restrictive
    allow_methods=["GET"],
    allow_headers=["*"],
)
```

This allows the browser to deliver the API response even when the HTML is opened from a `file://` URL.

---

## Security Notes

- **Do not expose the backend publicly** without adding authentication (e.g., API keys, OAuth).
- **Do not commit `sessions/`** — those JSON files contain authenticated browser sessions equivalent to login cookies.
- **Do not hardcode passwords** in `config.py` if you plan to share or publish the code. Use `os.getenv()` and a `.env` file instead.
- The scraper only reads your own Ollama Usage page; it does not send credentials or data anywhere else.

---

## Adapting to Ollama UI Changes

The collector parses the Ollama settings page by looking for specific text patterns:

- `Session usage` → followed by a percentage
- `Weekly usage` → followed by a percentage
- `Resets in` → followed by a time string
- Model lines ending in `requests`

If Ollama redesigns their settings page, update the selectors and regex patterns in
`app/collector.py` to match the new layout.

---

## Quick-Start Summary

```bash
# 1. Install dependencies
pip install -r requirements.txt
playwright install chromium

# 2. Configure your accounts
#    Edit app/config.py — add emails, passwords, and storage paths

# 3. Save sessions (one-time per account)
python -m app.collector --login

# 4. Start the backend (Terminal 1)
uvicorn app.main:app --host 127.0.0.1 --port 8000

# 5. Start the frontend server (Terminal 2)
cd frontend
python -m http.server 3000

# 6. Open the dashboard in your browser
#    http://127.0.0.1:3000/dashboard.html
```
