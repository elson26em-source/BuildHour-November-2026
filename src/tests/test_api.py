from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import app as server
from src.config.schema import normalize_api_key
from src.guardrails.templates import EMPTY_INDEX_MESSAGE


def test_normalize_api_key_strips_name_prefix_and_newline() -> None:
    assert normalize_api_key("GROQ_API_KEY=gsk_test\n", "GROQ_API_KEY") == "gsk_test"
    assert normalize_api_key(" gsk_test ", "GROQ_API_KEY") == "gsk_test"
    assert normalize_api_key(None, "GROQ_API_KEY") is None


def test_home_serves_chat_page_with_relative_api_paths() -> None:
    html = server.home()

    assert "GrowChat" in html
    assert 'fetch("/api/ask"' in html
    assert 'fetch("/api/config"' in html
    assert "http://" not in html.replace("https://fonts.googleapis.com", "")


def test_config_info_exposes_ui_defaults() -> None:
    info = server.config_info()

    assert info["examples"] == list(server.EXAMPLES)
    assert info["disclaimer"]
    assert isinstance(info["api_key_configured"], bool)


def test_health_reports_provider_model_and_key_presence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "GROQ_API_KEY=test-key\n")
    info = server.health()

    assert info["provider"] == "groq"
    assert info["model"] == "qwen/qwen3.8-27b"
    assert info["groq_api_key_present"] is True
    assert "test-key" not in str(info)

    monkeypatch.delenv("GROQ_API_KEY")
    assert server.health()["groq_api_key_present"] is False


def test_runtime_config_serves_bundled_index_and_logs_to_temp_dir() -> None:
    config = server.load_runtime_config()

    assert config.vector_db.persist_path == server.INDEX_SOURCE
    assert (config.vector_db.persist_path / "embeddings.npy").is_file()
    assert "grow-chat-" in str(config.paths.answers_dir)
    assert "grow-chat-" in str(config.paths.retrieval_dir)


def test_serialize_result_cleans_body_and_keeps_diagnostics() -> None:
    result = SimpleNamespace(
        request_id="abc",
        answer=(
            "A short fact.\nSource: https://groww.in/mutual-funds\n"
            "Last updated from sources: 2026-01-01"
        ),
        status="answered",
        intent="factual",
        citation_url="https://groww.in/mutual-funds",
        last_updated="2026-01-01",
        diagnostics={
            "llm_attempts": [{"strict": False, "error": None, "output": "secret"}],
            "validation": {"checks": {"sentence_limit": True}},
        },
        retrieval=SimpleNamespace(
            hits=(SimpleNamespace(chunk_id="c1", scheme="s", section="expense_ratio", score=0.91234),),
            candidates=(),
            fallback_source_url=None,
            retry_without_filters=True,
        ),
    )

    payload = server.serialize_result(result, "query")

    assert payload["answer"] == "A short fact."
    assert payload["citation_url"] == "https://groww.in/mutual-funds"
    assert payload["hits"][0]["score"] == 0.9123
    assert payload["retry_without_filters"] is True
    assert payload["diagnostics"]["llm_attempts"] == [
        {"strict": False, "error": None}
    ]


def test_serialize_result_flags_empty_index() -> None:
    result = SimpleNamespace(
        request_id="abc",
        answer=EMPTY_INDEX_MESSAGE,
        status="error",
        intent="factual",
        citation_url=None,
        last_updated=None,
        diagnostics={},
        retrieval=None,
    )

    payload = server.serialize_result(result, "query")

    assert payload["empty_index"] is True
    assert payload["answer"] == EMPTY_INDEX_MESSAGE


def test_ask_endpoint_returns_serialized_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    httpx = pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    result = SimpleNamespace(
        request_id="abc",
        answer="A short fact.\nSource: https://groww.in/mutual-funds\nLast updated from sources: 2026-01-01",
        status="answered",
        intent="factual",
        citation_url="https://groww.in/mutual-funds",
        last_updated="2026-01-01",
        diagnostics={},
        retrieval=None,
    )
    monkeypatch.setattr(
        server, "get_answerer", lambda: SimpleNamespace(answer=lambda query: result)
    )

    with TestClient(server.app) as client:
        response = client.post("/api/ask", json={"query": "expense ratio?"})

    assert response.status_code == 200
    assert response.json()["answer"] == "A short fact."
    assert httpx is not None


def test_ask_endpoint_rejects_empty_query() -> None:
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    with TestClient(server.app) as client:
        response = client.post("/api/ask", json={"query": "  "})

    assert response.status_code == 400


def test_static_page_exists() -> None:
    assert server.PAGE_PATH.is_file()
    assert Path(server.PAGE_PATH).read_text(encoding="utf-8").strip()
