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

st.subheader("Available Profiles")

profiles_url = f"{settings.api_base_url}/api/settings/profiles"

try:
    response = requests.get(profiles_url, timeout=5)
    if response.status_code == 200:
        profiles_response = response.json()
        profile_names = [profile["profile_name"] for profile in profiles_response["profiles"]]
        st.write(profile_names)
    else:
        st.warning(f"Profiles endpoint returned status code {response.status_code}.")
except requests.RequestException as exc:
    st.warning(f"Profiles endpoint is not reachable yet: {exc}")