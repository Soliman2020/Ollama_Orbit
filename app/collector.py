import asyncio
import json
import os
import re
from calendar import c
from typing import Dict, List

from playwright.async_api import async_playwright

from .config import ACCOUNTS, SETTINGS_URL


async def login_and_save_state(email: str, password: str, storage_path: str) -> None:
    """Interactive login for a single account, saves storage_state to disk.

    Run with a visible browser, log in manually, and once you reach the
    usage settings page, the state will be persisted for reuse.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto("https://ollama.com/login", wait_until="networkidle")

        # Adjust selectors to the real login form as needed.
        await page.fill("input[type='email']", email)
        # If password is required, uncomment and fill:
        await page.fill("input[type='password']", password)
        await page.click("button[type='submit']")

        # Wait until the settings page is reachable.
        await page.wait_for_url("**/settings", timeout=120_000)

        await context.storage_state(path=storage_path)
        await browser.close()


async def ensure_states_for_all_accounts():
    """Ensure each account has a valid storage_state; login if missing."""
    for cfg in ACCOUNTS:
        storage = cfg["storage"]
        if os.path.exists(storage):
            print(f"[skip] state already exists for {cfg['name']} -> {storage}")
            continue
        print(f"[login] creating state for {cfg['name']} ({cfg['email']})")
        await login_and_save_state(cfg["email"], cfg["password"], storage)
        print(f"[ok] saved storage to {storage}")


async def scrape_account(page, name: str, plan: str) -> Dict:
    """Scrape usage data for a single account from the settings page."""
    await page.goto(SETTINGS_URL, wait_until="networkidle")
    body_text = await page.text_content("body") or ""

    def extract_percent(prefix: str) -> float:
        pattern = rf"{prefix}\s+(\d+(?:\.\d+)?)% used"
        m = re.search(pattern, body_text)
        return float(m.group(1)) if m else 0.0

    def extract_reset(label: str) -> str:
        idx = body_text.find(label)
        if idx == -1:
            return ""
        snippet = body_text[idx : idx + 280]
        marker = "Resets in"
        i2 = snippet.find(marker)
        if i2 == -1:
            return ""
        line = snippet[i2 + len(marker) :].splitlines()[0].strip()
        return line

    session_percent = extract_percent("Session usage")
    weekly_percent = extract_percent("Weekly usage")

    session_reset = extract_reset("Session usage") or "n/a"
    weekly_reset = extract_reset("Weekly usage") or "n/a"

    return {
        "name": name,
        "plan": plan,
        "sessionPercent": round(session_percent),
        "weeklyPercent": round(weekly_percent),
        "sessionReset": session_reset,
        "weeklyReset": weekly_reset,
        "notes": "",
    }


async def collect_usage() -> List[Dict]:
    """Collect usage for all configured accounts using stored sessions."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        results: List[Dict] = []
        for cfg in ACCOUNTS:
            context = await browser.new_context(storage_state=cfg["storage"])
            page = await context.new_page()
            try:
                account_data = await scrape_account(page, cfg["name"], cfg["plan"])
                results.append(account_data)
            finally:
                await context.close()
        await browser.close()
    return results


async def interactive_login_flow():
    """Login for all accounts configured in ACCOUNTS, one by one."""
    await ensure_states_for_all_accounts()
    for cfg in ACCOUNTS:
        print(f"\n=== Login for {cfg['name']} ({cfg['email']}) ===")
        await login_and_save_state(cfg["email"], cfg["password"], cfg["storage"])
        print(f"Saved storage to {cfg['storage']}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Ollama usage collector")
    parser.add_argument(
        "--login", action="store_true", help="Run interactive login for all accounts"
    )
    parser.add_argument(
        "--snapshot",
        action="store_true",
        help="Collect a single snapshot and write JSON to disk",
    )
    args = parser.parse_args()

    if args.login:
        asyncio.run(interactive_login_flow())
    elif args.snapshot:
        data = asyncio.run(collect_usage())
        with open("ollama_usage_snapshot.json", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        print("Wrote ollama_usage_snapshot.json")
    else:
        parser.print_help()
