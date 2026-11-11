from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st

from src.config.loader import ConfigError, load_config, resolve_api_key
from src.generation.answerer import AnswerError, Answerer
from src.generation.validator import clean_body
from src.guardrails.templates import DISCLAIMER, EMPTY_INDEX_MESSAGE

EXAMPLES = (
    "What is the expense ratio of HDFC Large Cap Fund?",
    "What is the lock-in period for HDFC ELSS Tax Saver Fund?",
    "How can I download my capital-gains statement?",
)


@st.cache_resource
def get_answerer(config_path: str | None) -> Answerer:
    config = load_config(config_path, require_api_key=False)
    return Answerer(config)


def _is_empty_index(result) -> bool:
    return (
        result.status == "error"
        and result.answer.strip() == EMPTY_INDEX_MESSAGE
    )


def _render_diagnostics(result) -> None:
    with st.expander("Diagnostics"):
        st.write(f"**Request ID:** `{result.request_id}`")
        st.write(f"**Status:** `{result.status}`")
        st.write(f"**Intent:** `{result.intent}`")

        if result.diagnostics.get("pii_detected"):
            st.write("**PII detected:** `True` (query not persisted)")

        retrieval = result.retrieval
        if retrieval is not None:
            st.write("**Filters:**", retrieval.filters.as_dict())
            st.write(
                f"**Low confidence:** `{retrieval.low_confidence}`"
            )
            st.write(
                "**Section unavailable:** "
                f"`{retrieval.section_unavailable}`"
            )
            st.write(
                "**Scheme unavailable:** "
                f"`{retrieval.scheme_unavailable}`"
            )
            st.write(
                "**Retried without filters:** "
                f"`{retrieval.retry_without_filters}`"
            )
            hits = retrieval.hits or retrieval.candidates
            if hits:
                st.write("**Retrieved chunks:**")
                st.dataframe(
                    [
                        {
                            "chunk_id": hit.chunk_id,
                            "scheme": hit.scheme,
                            "section": hit.section,
                            "score": round(hit.score, 4),
                        }
                        for hit in hits
                    ],
                    use_container_width=True,
                    hide_index=True,
                )
            if retrieval.fallback_source_url:
                st.write(
                    "**Fallback source:** "
                    f"`{retrieval.fallback_source_url}`"
                )
            st.write(
                "**Retrieval artifact:** "
                f"`{result.diagnostics.get('retrieval_artifact')}`"
            )

        if result.validation is not None:
            st.write("**Validation checks:**")
            st.json(result.validation.checks)

        attempts = result.diagnostics.get("llm_attempts") or []
        if attempts:
            st.write("**LLM attempts:**")
            st.json(
                [
                    {
                        "strict": attempt["strict"],
                        "error": attempt["error"],
                    }
                    for attempt in attempts
                ]
            )

        answer_artifact = result.diagnostics.get("answer_artifact")
        st.write(
            "**Answer artifact:** "
            f"`{answer_artifact or 'not persisted'}`"
        )
        if result.diagnostics.get("error"):
            st.write(
                "**Error:** "
                f"`{result.diagnostics['error']}`"
            )


def _render_result(result) -> None:
    if _is_empty_index(result):
        st.warning(EMPTY_INDEX_MESSAGE)
        st.code("python -m src.cli ingest", language="powershell")
        _render_diagnostics(result)
        return

    st.markdown(clean_body(result.answer))

    if result.citation_url:
        st.link_button("Open source", result.citation_url)

    if result.last_updated:
        st.caption(
            f"Last updated from sources: {result.last_updated}"
        )

    _render_diagnostics(result)


def _render_history() -> None:
    for message in st.session_state.messages:
        with st.chat_message("user"):
            st.markdown(message["query"])
        with st.chat_message("assistant"):
            _render_result(message["result"])


def _handle_query(answerer: Answerer, query: str) -> None:
    try:
        with st.spinner("Checking the scraped sources..."):
            result = answerer.answer(query)
    except AnswerError as exc:
        st.error(f"Answer error: {exc}")
        return

    display_query = (
        "[Personal information removed]"
        if result.status == "pii"
        else query
    )
    st.session_state.messages.append(
        {"query": display_query, "result": result}
    )
    st.rerun()


def main() -> None:
    st.set_page_config(
        page_title="Groww MF FAQ Assistant",
        layout="centered",
    )

    st.title("Groww MF FAQ Assistant")
    st.write(
        "Ask factual questions about the HDFC mutual fund pages in the "
        "knowledge base."
    )
    st.info(DISCLAIMER)
    st.sidebar.info(DISCLAIMER)
    st.sidebar.write(
        "The assistant answers only from the five scraped Groww pages. "
        "It does not provide investment advice."
    )

    config_path = st.sidebar.text_input(
        "Config path",
        value="",
        placeholder="config.yaml",
    ).strip() or None

    try:
        answerer = get_answerer(config_path)
    except ConfigError as exc:
        st.error(f"Config error: {exc}")
        st.stop()

    if resolve_api_key(answerer.config) is None:
        st.sidebar.warning(
            f"No {answerer.config.llm.api_key_env} detected. Factual "
            "answers will use the safe fallback until it is set in .env."
        )

    if "messages" not in st.session_state:
        st.session_state.messages = []

    st.write("**Try an example:**")
    columns = st.columns(len(EXAMPLES))
    for column, example in zip(columns, EXAMPLES):
        with column:
            if st.button(example, use_container_width=True):
                _handle_query(answerer, example)

    _render_history()

    prompt = st.chat_input("Ask a factual question about these funds...")
    if prompt:
        _handle_query(answerer, prompt)


if __name__ == "__main__":
    main()
