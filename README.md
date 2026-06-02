# Ollama Usage Monitor

A self-hosted usage dashboard for multiple Ollama Cloud accounts.

- Backend: FastAPI + Playwright collector that logs into each account (via stored sessions) and scrapes the **Usage** settings page.
- Frontend: Single-file HTML dashboard that calls the backend and visualizes per-account session and weekly usage.
- Scheduler: A background job that periodically refreshes usage data for all configured accounts.

The goal is to avoid manually logging into six accounts and checking `https://ollama.com/settings` for each one. Instead, you see all accounts in one auto-refreshing dashboard.

---

## Features

- Track **session** and **weekly** percentage usage for several Ollama accounts on one screen (values from the Usage page, e.g. “Session usage 0% used”, “Weekly usage 38.2% used”). 
- See **reset windows** such as “Resets in 1 hour” for session and “Resets in 6 days” for weekly usage. 
- Auto-refresh usage snapshots every N minutes via a background collector job.
- Per-account cards and a table view (in the full dashboard) for fast scanning.
- Export current dataset as JSON from the frontend for analysis or backup.
- Designed to support exactly what the Ollama Usage page exposes, including plan, limits, and reset behavior. 

---

## How it works

- **Data source**:
  - The app reads usage data from each account’s **Usage** settings screen at `https://ollama.com/settings`. 
  - It extracts fields like session usage %, weekly usage %, reset phrases (“Resets in …”), and model usage lines that mention requests. 

- **Authentication**:
  - Each Ollama account uses email + password to log in once.
  - The login flow saves a Playwright `storage_state` file per account so subsequent collection runs can be fully automated and headless.
  - Storage state files (e.g. `state_account_1.json`) act as persistent sessions, similar to browser profiles.

- **Collector**:
  - A collector script iterates over all configured accounts.
  - For each account it:
    - Loads the stored session state.
    - Opens `https://ollama.com/settings`.
    - Reads the page content and parses:
      - Session usage percentage (e.g. “Session usage 0% used”).
      - Weekly usage percentage (e.g. “Weekly usage 38.2% used”).
      - Session reset text (e.g. “Resets in 1 hour”).
      - Weekly reset text (e.g. “Resets in 6 days”).
      - Per-model usage lines (e.g. “minimax-m2.5: 11 requests”). 
    - Produces a normalized JSON object per account with:
      - `name`, `plan`
      - `sessionPercent`, `weeklyPercent`
      - `sessionReset`, `weeklyReset`
      - `models` (list of model usage strings)
      - `notes` (optional)

- **Backend API**:
  - The backend is a FastAPI app exposing:
    - `GET /usage` which returns `{"accounts": [...], "error": ...}` from the latest snapshot.
    - `GET /` which returns a simple status and number of accounts.
  - A scheduler (via APScheduler) runs `collect_usage()` periodically based on a refresh interval in minutes.

- **Frontend**:
  - A single HTML file acts as the dashboard.
  - It periodically calls `http://localhost:8000/usage`.
  - It expects an array of account objects conforming to the JSON shape produced by the collector.
  - It renders:
    - Global KPI cards (number of accounts, highest weekly load, etc.).
    - Per-account cards (session/weekly bars, reset windows, model badges).
    - A table view for quick comparison across accounts.

---

## Project structure

Recommended structure for the repository:

```text
ollama-usage-monitor/
  app/
    __init__.py
    config.py         # accounts, passwords (or env vars), refresh interval, settings URL
    collector.py      # login and scraping logic, plus CLI helpers
    main.py           # FastAPI + scheduler + API endpoints
  frontend/
    ollama-usage-dashboard.html  # single-file dashboard consuming /usage
  requirements.txt
  README.md
```

---

## Prerequisites

- Python 3.10+
- Ollama Cloud accounts that have access to the **Usage** settings page at `https://ollama.com/settings`. 
- Basic familiarity with:
  - FastAPI (for running the backend API). 
  - Playwright (for browser automation and persisted auth state). 
  - APScheduler or cron-like scheduling for periodic tasks. 

---

## Configuration

All configuration lives in `app/config.py`:

- `ACCOUNTS`:
  - List of dictionaries, one per Ollama account.
  - Each entry includes:
    - `name` (label for the dashboard, e.g. “Work-01”).
    - `plan` (e.g. “Developer” or “Free”).
    - `email` (used for login).
    - `password` (used for login; can be sourced from environment variables instead of hardcoded).
    - `storage` (path/name of the Playwright storage state file).

- `REFRESH_MINUTES`:
  - Global integer defining how often the scheduler should refresh usage data.

- `SETTINGS_URL`:
  - Defaults to `https://ollama.com/settings`.
  - Change here if Ollama ever moves the usage page. 

---

## Usage workflow (high level)

1. **Install dependencies**  
   - Use `requirements.txt` to install FastAPI, Playwright, APScheduler, and uvicorn. 

2. **Configure accounts**  
   - Edit `ACCOUNTS` with the six Ollama accounts you want to monitor.
   - Provide emails and passwords (or environment variables), plus unique storage file names.

3. **Create and save sessions**  
   - Run the login mode in the collector so each account performs one full login.
   - This writes the `storage_state` JSON for each account, which Playwright will reuse as an authenticated session.

4. **Run the backend**  
   - Start the FastAPI app (e.g. with uvicorn).
   - On startup, it can:
     - Verify or create storage state files (optional).
     - Immediately refresh usage data.
   - The APScheduler job runs at the configured interval to keep `usage_cache` up to date.

5. **Open the dashboard**  
   - Open the HTML dashboard file from `frontend/` in a browser.
   - The dashboard calls `GET /usage`, reads `accounts`, and renders the data.
   - It auto-refreshes the data on a timer to stay in sync with the backend.

---

## Data model (JSON shape)

Each account in the `/usage` response has this structure:

- `name`: string – logical label for the account (e.g. “Work-01”).
- `plan`: string – plan from your own config (e.g. “Free”, “Developer”, “Pro”).
- `sessionPercent`: number – parsed percentage from “Session usage X% used”. 
- `weeklyPercent`: number – parsed percentage from “Weekly usage X% used”. 
- `sessionReset`: string – parsed text after “Resets in …” near the session usage section (e.g. “1 hour”). 
- `weeklyReset`: string – parsed text after “Resets in …” near the weekly usage section (e.g. “6 days”). 
- `notes`: string – optional notes field for internal comments (e.g. client name, environment, purpose).

This structure is intentionally simple so you can:

- Feed it directly into dashboards.
- Export it as JSON from the frontend and analyze it in Python or other tools.

---

## Security and privacy notes

- This project is intended for **local use** on your own machine or a private server:
  - Do not expose the FastAPI backend publicly without adding authentication.
  - Do not commit plain-text passwords to a public GitHub repo.
- Consider replacing `password` fields in `config.py` with environment-variable lookups (for example, `os.getenv("OLLAMA_PWD_1")`) so secrets are not stored in the repository.
- Storage state files contain authenticated session data; treat them as sensitive and keep them outside public version control.
- The scraper reads only your own Usage page; it does not send credentials or usage data anywhere else.

---

## Adapting to UI changes

- The collector relies on the current structure and wording of the Usage page:
  - Phrases like “Session usage”, “Weekly usage”, “Resets in”, and model lines ending with “requests”. 
- If Ollama changes the Usage layout or wording, you might need to:
  - Adjust the text patterns and selectors in the collector to match the new HTML.
  - Update the parsing logic that extracts percentages, reset windows, and model usage.

Keeping this README updated with any future changes in Ollama’s Usage page will help maintain the monitor over time.
