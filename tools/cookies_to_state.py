# tools/cookies_to_state.py
#
# Converts a Cookie-Editor JSON export from your real Chrome browser
# into a Playwright storage_state JSON file that collector.py can reuse.
#
# Usage:
#   python tools/cookies_to_state.py <input_cookies.json> <output_state.json>
#
# Example:
#   python tools/cookies_to_state.py cookies_account_1.json app/state_account_1.json

import json
import sys
from pathlib import Path

SAME_SITE_MAP = {
    "Strict": "Strict",
    "Lax": "Lax",
    "None": "None",
    "no_restriction": "None",
    "unspecified": "Lax",
    "": "Lax",
}


def convert(cookie_file: str, state_file: str) -> None:

    # ── Read the Cookie-Editor export ─────────────────────────────────────────
    input_path = Path(cookie_file)
    if not input_path.exists():
        print(f"[error] Input file not found: {cookie_file}")
        sys.exit(1)

    raw = input_path.read_text(encoding="utf-8")

    try:
        cookies = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"[error] Could not parse JSON from {cookie_file}: {e}")
        sys.exit(1)

    if not isinstance(cookies, list):
        print(
            f"[error] Expected a JSON array of cookies.\n"
            f"        Got: {type(cookies).__name__}\n"
            f"        Make sure you used Cookie-Editor → Export → Export as JSON."
        )
        sys.exit(1)

    # ── Convert each cookie to Playwright format ───────────────────────────────
    playwright_cookies = []
    skipped = 0

    for c in cookies:
        name = c.get("name", "")
        value = c.get("value", "")

        # Skip cookies with no name — Playwright rejects them.
        if not name:
            skipped += 1
            continue

        domain = c.get("domain", "")

        # Playwright requires a leading dot for domain-level cookies.
        if domain and not domain.startswith(".") and not domain.startswith("localhost"):
            domain = "." + domain

        same_site_raw = c.get("sameSite", "Lax")
        same_site = SAME_SITE_MAP.get(same_site_raw, "Lax")

        # Cookie-Editor uses "expirationDate"; Playwright uses "expires".
        # Session cookies have no expiration → use -1.
        expires = c.get("expirationDate", c.get("expires", -1))
        if expires is None:
            expires = -1

        playwright_cookies.append(
            {
                "name": name,
                "value": value,
                "domain": domain,
                "path": c.get("path", "/"),
                "expires": expires,
                "httpOnly": c.get("httpOnly", False),
                "secure": c.get("secure", False),
                "sameSite": same_site,
            }
        )

    # ── Build Playwright storage_state structure ───────────────────────────────
    state = {
        "cookies": playwright_cookies,
        "origins": [],
    }

    # ── Write output file ──────────────────────────────────────────────────────
    output_path = Path(state_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(state, indent=2),
        encoding="utf-8",
    )

    # ── Summary ────────────────────────────────────────────────────────────────
    print(
        f"[ok] Converted {len(playwright_cookies)} cookies  (skipped {skipped} unnamed)"
    )
    print(f"     Input  : {cookie_file}")
    print(f"     Output : {state_file}")


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(
            "Usage:\n"
            "  python tools/cookies_to_state.py <input_cookies.json> <output_state.json>\n\n"
            "Example:\n"
            "  python tools/cookies_to_state.py cookies_account_1.json app/state_account_1.json"
        )
        sys.exit(1)

    convert(sys.argv[1], sys.argv[2])
