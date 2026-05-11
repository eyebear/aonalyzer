import streamlit as st

from app.profiles.default_profiles import get_balanced_research_default

st.set_page_config(
    page_title="Ao Ao Analyzer",
    page_icon="",
    layout="wide",
)

st.title("Ao Ao Analyzer")

st.caption(
    "Local, Dockerized, AI-assisted equity and options research operating system."
)

st.subheader("Project Status")
st.write("Phase 0 foundation files are initialized.")

st.subheader("Product Boundary")
st.write("Research-only. No broker integration. No auto-trading.")

st.subheader("Default Strategy Profile")
st.json(get_balanced_research_default())
