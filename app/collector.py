import argparse
import asyncio
import json
import os
import re
from typing import Dict, List

from playwright.async_api import async_playwright

from .config import ACCOUNTS, SETTINGS_URL

# ---------------------------------------------------------------------------
# Chrome path helpers
# ---------------------------------------------------------------------------


def _get_chrome_path() -> str | None:
    """
    Return the path to the real Chrome or Edge installation on Windows.
    Returns None if not found (falls back to Playwright's bundled Chromium).
    """
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


# ---------------------------------------------------------------------------
# Option 2 — Manual login: open real browser, let user log in, save session
# ---------------------------------------------------------------------------


async def save_state_from_manual_login(
    account_name: str,
    storage_path: str,
) -> None:
    """
    Open a visible browser window (real Chrome if available, else Chromium),
    navigate to the Ollama sign-in page, and wait for the user to log in
    manually. Once the user reaches any ollama.com page after login,
    the authenticated session is saved to `storage_path` for reuse.

    This is the recommended login method because it fully bypasses
    Cloudflare's bot detection — the user clicks and types themselves.
    """
    chrome_path = _get_chrome_path()

    async with async_playwright() as p:
        launch_kwargs = {
            "headless": False,
            "args": ["--disable-blink-features=AutomationControlled"],
        }
        if chrome_path:
            launch_kwargs["executable_path"] = chrome_path
            print(f"[browser] Using real Chrome at: {chrome_path}")
        else:
            print("[browser] Real Chrome not found, using Playwright Chromium.")

        browser = await p.chromium.launch(**launch_kwargs)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/136.0.0.0 Safari/537.36"
            ),
        )

        # Remove the webdriver flag to reduce bot signals.
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        page = await context.new_page()

        await page.goto(
            "https://signin.ollama.com/",
            wait_until="domcontentloaded",
            timeout=60_000,
        )

        print(
            f"\n{'=' * 55}\n"
            f"  [MANUAL LOGIN REQUIRED] Account: {account_name}\n"
            f"{'=' * 55}\n"
            f"  A browser window has opened.\n"
            f"  Please:\n"
            f"    1. Enter your email and click Continue.\n"
            f"    2. Solve any CAPTCHA that appears.\n"
            f"    3. Enter your password and click Continue.\n"
            f"  The script will save your session automatically\n"
            f"  once you are redirected to ollama.com.\n"
            f"  You have up to 5 minutes.\n"
            f"{'=' * 55}\n"
        )

        # Wait for the user to finish logging in manually.
        # Detects the redirect back to ollama.com after successful login.
        await page.wait_for_url(
            "https://ollama.com/**",
            timeout=300_000,  # 5 minutes
        )

        # Persist the authenticated session to disk.
        await context.storage_state(path=storage_path)
        print(f"[ok] Session saved to: {storage_path}\n")

        await browser.close()


async def ensure_states_for_all_accounts() -> None:
    """
    Check each configured account. If its storage_state file does not exist,
    trigger a manual login for that account to create it.
    Already-logged-in accounts (existing state files) are skipped.
    """
    for cfg in ACCOUNTS:
        storage = cfg["storage"]
        if os.path.exists(storage):
            print(f"[skip] Session already exists for {cfg['name']} -> {storage}")
            continue
        print(f"\n[login needed] {cfg['name']} ({cfg['email']}) has no saved session.")
        await save_state_from_manual_login(cfg["name"], storage)


# ---------------------------------------------------------------------------
# Scraping: visit /settings and extract usage data
# ---------------------------------------------------------------------------


async def scrape_account(page, name: str, plan: str) -> Dict:
    """
    Navigate to the Ollama settings/usage page and extract:
    - Session usage percentage and reset window.
    - Weekly usage percentage and reset window.
    - Per-model request counts for both session and weekly usage.
    """
    await page.goto(
        SETTINGS_URL,
        wait_until="domcontentloaded",
        timeout=60_000,
    )

    # Wait for the page body to be populated.
    await page.wait_for_selector("body", timeout=15_000)
    body_text = await page.text_content("body") or ""

    def extract_percent(label: str) -> float:
        pattern = rf"{label}\s+(\d+(?:\.\d+)?)%\s+used"
        m = re.search(pattern, body_text)
        return float(m.group(1)) if m else 0.0

    def extract_reset(label: str) -> str:
        idx = body_text.find(label)
        if idx == -1:
            return "n/a"
        snippet = body_text[idx : idx + 280]
        marker = "Resets in"
        i2 = snippet.find(marker)
        if i2 == -1:
            return "n/a"
        line = snippet[i2 + len(marker) :].splitlines()[0].strip()
        return line or "n/a"

    session_percent = extract_percent("Session usage")
    weekly_percent = extract_percent("Weekly usage")
    session_reset = extract_reset("Session usage")
    weekly_reset = extract_reset("Weekly usage")

    # ------------------------------------------------------------------
    # Extract per-model usage from data-usage-segment elements.
    # Each meter (session + weekly) contains buttons with:
    #   data-model="kimi-k2.6" data-requests="2"
    # ------------------------------------------------------------------
    session_models: List[Dict] = []
    weekly_models: List[Dict] = []

    try:
        meters = await page.query_selector_all("[data-usage-meter]")
        for meter in meters:
            track = await meter.query_selector("[data-usage-track]")
            if not track:
                continue
            aria_label = await track.get_attribute("aria-label") or ""

            segments = await meter.query_selector_all("[data-usage-segment]")
            models_for_meter: List[Dict] = []
            for seg in segments:
                model_name = await seg.get_attribute("data-model")
                requests_str = await seg.get_attribute("data-requests")
                if model_name and requests_str:
                    try:
                        req_count = int(requests_str)
                    except ValueError:
                        req_count = 0
                    models_for_meter.append({
                        "model": model_name,
                        "requests": req_count,
                    })

            if "Session" in aria_label:
                session_models = models_for_meter
            elif "Weekly" in aria_label:
                weekly_models = models_for_meter
    except Exception:
        # If JS attribute extraction fails, fall back to no model data.
        pass

    # Derive a top-level "models" list (unique model names from either bucket).
    all_model_names = {m["model"] for m in session_models + weekly_models}

    return {
        "name": name,
        "plan": plan,
        "sessionPercent": round(session_percent),
        "weeklyPercent": round(weekly_percent),
        "sessionReset": session_reset,
        "weeklyReset": weekly_reset,
        "models": sorted(all_model_names) if all_model_names else [],
        "sessionModels": session_models,
        "weeklyModels": weekly_models,
        "notes": "",
    }


# ---------------------------------------------------------------------------
# Collector: run scraping for all accounts using saved sessions
# ---------------------------------------------------------------------------


async def collect_usage() -> List[Dict]:
    """
    Iterate over all configured accounts, load each account's saved
    storage_state, visit the settings page, and return a list of usage dicts.
    Runs headless because no login is needed (sessions are already saved).
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        results: List[Dict] = []

        for cfg in ACCOUNTS:
            storage = cfg["storage"]

            if not os.path.exists(storage):
                print(
                    f"[warn] No session file found for {cfg['name']} "
                    f"({storage}). Skipping. Run --manual to create it."
                )
                results.append(
                    {
                        "name": cfg["name"],
                        "plan": cfg["plan"],
                        "sessionPercent": 0,
                        "weeklyPercent": 0,
                        "sessionReset": "no session",
                        "weeklyReset": "no session",
                        "models": [],
                        "sessionModels": [],
                        "weeklyModels": [],
                        "notes": "Run --manual to log in.",
                    }
                )
                continue

            context = await browser.new_context(storage_state=storage)
            page = await context.new_page()
            try:
                data = await scrape_account(page, cfg["name"], cfg["plan"])
                results.append(data)
                print(f"[ok] Collected usage for {cfg['name']}")
            except Exception as exc:
                print(f"[error] Failed to collect {cfg['name']}: {exc}")
                results.append(
                    {
                        "name": cfg["name"],
                        "plan": cfg["plan"],
                        "sessionPercent": 0,
                        "weeklyPercent": 0,
                        "sessionReset": "error",
                        "weeklyReset": "error",
                        "models": [],
                        "sessionModels": [],
                        "weeklyModels": [],
                        "notes": str(exc),
                    }
                )
            finally:
                await context.close()

        await browser.close()
    return results


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Ollama Usage Collector",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--manual",
        action="store_true",
        help=(
            "Open a real browser for each account that has no saved session.\n"
            "Log in manually to bypass Cloudflare. Session is saved automatically."
        ),
    )
    parser.add_argument(
        "--manual-account",
        metavar="NAME",
        help=(
            "Re-run manual login for a specific account by its name\n"
            "(e.g. --manual-account Work-01). Overwrites existing session."
        ),
    )
    parser.add_argument(
        "--snapshot",
        action="store_true",
        help=(
            "Collect a single usage snapshot for all accounts\n"
            "and write the result to ollama_usage_snapshot.json."
        ),
    )
    args = parser.parse_args()

    if args.manual:
        # Login for all accounts that have no saved session file.
        asyncio.run(ensure_states_for_all_accounts())

    elif args.manual_account:
        # Re-login for a specific account by name (useful if session expired).
        target = next((c for c in ACCOUNTS if c["name"] == args.manual_account), None)
        if target is None:
            print(
                f"[error] No account named '{args.manual_account}' found in config.\n"
                f"        Available names: {[c['name'] for c in ACCOUNTS]}"
            )
        else:
            asyncio.run(save_state_from_manual_login(target["name"], target["storage"]))

    elif args.snapshot:
        # Collect usage snapshot and write to JSON.
        data = asyncio.run(collect_usage())
        out_file = "ollama_usage_snapshot.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        print(f"\n[ok] Wrote snapshot to {out_file}")

    else:
        parser.print_help()
