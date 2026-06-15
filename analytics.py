"""Ollama-Orbit historical analytics — Streamlit companion.

Reads the new GET /usage/history endpoint from the FastAPI backend
and renders three tabs: weekly trend, model breakdown, leaderboard.

Run:
    streamlit run analytics.py
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone

import pandas as pd
import streamlit as st


# ponytail: stdlib HTTP — no requests dep.
def _fetch(url: str, timeout: float = 5.0) -> dict | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError):
        return None


@st.cache_data(ttl=60)
def fetch_history(base_url: str, days: int) -> dict | None:
    base = base_url.rstrip("/")
    return _fetch(f"{base}/usage/history?days={days}")


def _latest_per_account(snapshots: pd.DataFrame) -> pd.DataFrame:
    if snapshots.empty:
        return snapshots
    return (
        snapshots.sort_values("ts")
        .groupby("account", as_index=False)
        .tail(1)
        .reset_index(drop=True)
    )


def _earliest_in_window(
    snapshots: pd.DataFrame, cutoff_iso: str
) -> pd.DataFrame:
    """Return the first snapshot per account at-or-after cutoff_iso."""
    if snapshots.empty:
        return snapshots
    window = snapshots[snapshots["ts"] >= cutoff_iso]
    if window.empty:
        return window
    return (
        window.sort_values("ts")
        .groupby("account", as_index=False)
        .head(1)
        .reset_index(drop=True)
    )


def main() -> None:
    st.set_page_config(
        page_title="Ollama-Orbit Analytics", layout="wide"
    )
    st.title("Ollama-Orbit — Historical Analytics")

    with st.sidebar:
        st.header("Backend")
        default_url = os.environ.get("ORBIT_URL", "http://127.0.0.1:8000")
        base_url = st.text_input("Backend URL", value=default_url)
        days = st.radio(
            "Range", [1, 7, 30], index=1, horizontal=True
        )
        st.caption(
            "Snapshots are recorded every refresh "
            "(see REFRESH_MINUTES in app/config.py)."
        )

    data = fetch_history(base_url, days)
    if data is None:
        st.error(
            f"Can't reach backend at {base_url}. "
            "Is uvicorn running? Start it with: "
            "`uvicorn app.main:app --host 127.0.0.1 --port 8000`"
        )
        st.stop()

    snapshots = pd.DataFrame(data.get("snapshots", []))
    models = pd.DataFrame(data.get("models", []))

    if len(snapshots) < 2:
        st.info(
            "Waiting for the scheduler — at least two snapshots are "
            "needed to draw a trend. The first one lands within "
            "REFRESH_MINUTES of backend startup."
        )
        st.stop()

    tab_trend, tab_models, tab_board = st.tabs(
        ["Weekly trend", "Model breakdown", "Leaderboard"]
    )

    # --- Weekly trend ----------------------------------------------------
    with tab_trend:
        st.subheader(f"Weekly % over the last {days} day(s)")
        # Defensive: backend always returns these columns; coerce numerics.
        snapshots["weeklyPercent"] = pd.to_numeric(
            snapshots["weeklyPercent"], errors="coerce"
        )
        snapshots["sessionPercent"] = pd.to_numeric(
            snapshots["sessionPercent"], errors="coerce"
        )
        pivot = snapshots.pivot_table(
            index="ts",
            columns="account",
            values="weeklyPercent",
            aggfunc="last",
        ).sort_index()
        st.line_chart(pivot)

        st.subheader("Session % over the same window")
        pivot_s = snapshots.pivot_table(
            index="ts",
            columns="account",
            values="sessionPercent",
            aggfunc="last",
        ).sort_index()
        st.line_chart(pivot_s)

    # --- Model breakdown -------------------------------------------------
    with tab_models:
        st.subheader("Per-model request counts")
        if models.empty:
            st.info("No model-level data in this window yet.")
        else:
            accounts = sorted(models["account"].unique().tolist())
            account = st.selectbox("Account", accounts)
            bucket = st.radio(
                "Bucket", ["weekly", "session"], horizontal=True
            )
            sub = models[
                (models["account"] == account)
                & (models["bucket"] == bucket)
            ]
            if sub.empty:
                st.info(f"No {bucket} model data for {account} yet.")
            else:
                pivot_m = sub.pivot_table(
                    index="ts",
                    columns="model",
                    values="requests",
                    aggfunc="sum",
                ).sort_index()
                st.bar_chart(pivot_m)

    # --- Leaderboard -----------------------------------------------------
    with tab_board:
        st.subheader("Current weekly usage, ranked")
        latest = _latest_per_account(snapshots).sort_values(
            "weeklyPercent", ascending=False
        )
        # Delta: pick the earliest snapshot in the window per account.
        try:
            cutoff_dt = datetime.fromisoformat(
                snapshots["ts"].min()
            )  # window start = oldest returned
        except ValueError:
            cutoff_dt = datetime.now(timezone.utc)
        earliest = _earliest_in_window(snapshots, cutoff_dt.isoformat())
        merged = latest.merge(
            earliest[["account", "weeklyPercent"]],
            on="account",
            how="left",
            suffixes=("", "_start"),
        )
        merged["delta (pp)"] = (
            merged["weeklyPercent"] - merged["weeklyPercent_start"]
        ).round(1)
        view = merged.rename(
            columns={
                "account": "Account",
                "plan": "Plan",
                "weeklyPercent": "Weekly %",
                "sessionPercent": "Session %",
                "ts": "Last seen",
                "weeklyReset": "Weekly reset",
            }
        )[
            [
                "Account",
                "Plan",
                "Weekly %",
                "Session %",
                "delta (pp)",
                "Last seen",
                "Weekly reset",
            ]
        ]
        st.dataframe(
            view,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Weekly %": st.column_config.ProgressColumn(
                    "Weekly %", min_value=0, max_value=100, format="%.1f"
                ),
                "Session %": st.column_config.ProgressColumn(
                    "Session %", min_value=0, max_value=100, format="%.1f"
                ),
            },
        )


if __name__ == "__main__":
    main()
