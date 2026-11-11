from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from streamlit.testing.v1 import AppTest

from src.app.streamlit_app import _is_empty_index
from src.guardrails.templates import DISCLAIMER, EMPTY_INDEX_MESSAGE

PROJECT_ROOT = Path(__file__).resolve().parents[2]
APP_PATH = PROJECT_ROOT / "src" / "app" / "streamlit_app.py"


def test_streamlit_app_renders_examples_and_disclaimer() -> None:
    app = AppTest.from_file(str(APP_PATH), default_timeout=60)
    app.run()

    assert not app.exception
    assert app.title[0].value == "Groww MF FAQ Assistant"
    assert [button.label for button in app.button] == [
        "What is the expense ratio of HDFC Large Cap Fund?",
        "What is the lock-in period for HDFC ELSS Tax Saver Fund?",
        "How can I download my capital-gains statement?",
    ]
    assert DISCLAIMER in [info.value for info in app.info]


def test_streamlit_app_redacts_pii_query() -> None:
    app = AppTest.from_file(str(APP_PATH), default_timeout=60)
    app.run()
    app.chat_input[0].set_value("My PAN is ABCDE1234F").run()

    assert not app.exception
    rendered = "\n".join(item.value for item in app.markdown)
    assert "ABCDE1234F" not in rendered
    assert "[Personal information removed]" in rendered
    assert "personal information" in rendered.lower()


def test_is_empty_index_uses_friendly_ingestion_message() -> None:
    empty = SimpleNamespace(status="error", answer=EMPTY_INDEX_MESSAGE)
    other = SimpleNamespace(status="error", answer="Different error")

    assert _is_empty_index(empty)
    assert not _is_empty_index(other)
