import requests
import streamlit as st

from app.core.config import get_settings
from app.profiles.default_profiles import get_balanced_research_default

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

st.subheader("Default Strategy Profile")
st.json(get_balanced_research_default())