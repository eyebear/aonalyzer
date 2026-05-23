"""Runtime render smoke test for every Streamlit page in both view modes.

Uses Streamlit's ``AppTest`` to actually execute each page script (not just
``ast.parse`` it). Catches the class of bug where a page renders in beginner
mode but raises in advanced mode (e.g. a bare ``st.json(...) if ... else
st.write(...)`` ternary whose return value trips Streamlit's magic-write
introspection). The API is not running during tests, so this also verifies
every page degrades gracefully when the backend is unreachable.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PAGE_FILES = [PROJECT_ROOT / "app" / "dashboard" / "main.py"] + sorted(
    (PROJECT_ROOT / "app" / "dashboard" / "pages").glob("[0-9]*.py")
)

VIEW_MODES = ("BEGINNER", "ADVANCED")


@pytest.mark.parametrize("view_mode", VIEW_MODES)
@pytest.mark.parametrize("page", PAGE_FILES, ids=lambda p: p.name)
def test_page_renders_without_exception(page: Path, view_mode: str) -> None:
    at = AppTest.from_file(str(page), default_timeout=60)
    at.session_state["global_view_mode"] = view_mode
    at.run()

    rendered_exceptions = list(at.exception)
    assert not rendered_exceptions, (
        f"{page.name} raised in {view_mode} mode: "
        f"{[f'{e.type}: {e.message}' for e in rendered_exceptions]}"
    )
