from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import requests
import streamlit as st

from app.core.config import get_settings

settings = get_settings()

st.set_page_config(
    page_title=settings.app_name,
    layout="wide",
)

st.title(settings.app_name)

st.caption("Local equity and options research platform.")

st.subheader("System Status")

api_health_url = f"{settings.api_base_url}/health"

try:
    response = requests.get(api_health_url, timeout=5)
    if response.status_code == 200:
        st.success("FastAPI service is reachable.")
        st.json(response.json())
    else:
        st.warning(f"FastAPI service returned status code {response.status_code}.")
except requests.RequestException as exc:
    st.warning(f"FastAPI service is not reachable yet: {exc}")

st.subheader("Manual Refresh Controls")

refresh_columns = st.columns(4)

refresh_buttons = [
    ("Refresh All", "/api/agent/refresh/all"),
    ("Refresh Market Data", "/api/agent/refresh/market-data"),
    ("Refresh Options", "/api/agent/refresh/options"),
    ("Refresh News", "/api/agent/refresh/news"),
    ("Refresh Filings", "/api/agent/refresh/filings"),
    ("Refresh Earnings", "/api/agent/refresh/earnings"),
    ("Refresh IV Risk", "/api/agent/refresh/iv-risk"),
    ("Run Recommendations", "/api/agent/run/recommendations"),
]

for index, (label, endpoint) in enumerate(refresh_buttons):
    with refresh_columns[index % 4]:
        if st.button(label):
            try:
                response = requests.post(f"{settings.api_base_url}{endpoint}", timeout=10)
                if response.status_code == 200:
                    st.success(f"{label} job recorded.")
                    st.json(response.json())
                else:
                    st.warning(f"{label} returned status code {response.status_code}.")
            except requests.RequestException as exc:
                st.warning(f"{label} failed: {exc}")

st.subheader("Active Strategy Profile")

profile_url = f"{settings.api_base_url}/api/settings/profile"

try:
    response = requests.get(profile_url, timeout=5)
    if response.status_code == 200:
        profile_response = response.json()
        st.success(
            "Active profile loaded: "
            f"{profile_response['active_profile_name']} "
            f"({profile_response['active_profile_version']})"
        )
        st.json(profile_response["profile"])
    else:
        st.warning(f"Profile endpoint returned status code {response.status_code}.")
except requests.RequestException as exc:
    st.warning(f"Profile endpoint is not reachable yet: {exc}")

st.subheader("Watchlist Tickers")

tickers_url = f"{settings.api_base_url}/api/tickers"

try:
    response = requests.get(tickers_url, timeout=5)
    if response.status_code == 200:
        tickers_response = response.json()
        st.success(f"Loaded {tickers_response['count']} active tickers.")
        st.dataframe(tickers_response["tickers"], use_container_width=True)
    else:
        st.warning(f"Ticker endpoint returned status code {response.status_code}.")
except requests.RequestException as exc:
    st.warning(f"Ticker endpoint is not reachable yet: {exc}")

st.subheader("Agent Status")

agent_status_url = f"{settings.api_base_url}/api/agent/status"

try:
    response = requests.get(agent_status_url, timeout=5)
    if response.status_code == 200:
        st.json(response.json())
    else:
        st.warning(f"Agent status endpoint returned status code {response.status_code}.")
except requests.RequestException as exc:
    st.warning(f"Agent status endpoint is not reachable yet: {exc}")

st.subheader("Recent Agent Runs")

agent_runs_url = f"{settings.api_base_url}/api/agent/runs"

try:
    response = requests.get(agent_runs_url, timeout=5)
    if response.status_code == 200:
        runs_response = response.json()
        st.dataframe(runs_response["runs"], use_container_width=True)
    else:
        st.warning(f"Agent runs endpoint returned status code {response.status_code}.")
except requests.RequestException as exc:
    st.warning(f"Agent runs endpoint is not reachable yet: {exc}")