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

STYLES = """
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&display=swap');

html, body, .stApp, [class*="css"] {
    font-family: 'Plus Jakarta Sans', sans-serif;
}

.stApp {
    background:
        radial-gradient(circle at 18% 0%, #101a2e 0%, #0B0F17 42%, #090D14 100%);
    color: #E2E8F0;
}

[data-testid="stHeader"] {
    background: rgba(11, 15, 23, 0.65);
    backdrop-filter: blur(10px);
    border-bottom: 1px solid rgba(30, 41, 59, 0.45);
}

[data-testid="stSidebar"],
[data-testid="stSidebarContent"] {
    background: #090D14;
    border-right: 1px solid rgba(30, 41, 59, 0.8);
}

[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span,
[data-testid="stSidebar"] label {
    color: #94A3B8;
}

[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 {
    color: #E2E8F0;
}

h1 {
    font-family: 'Plus Jakarta Sans', sans-serif;
    font-weight: 800 !important;
    letter-spacing: -0.02em;
    background: linear-gradient(90deg, #FFFFFF 0%, #C7D2FE 55%, #6EE7B7 100%);
    -webkit-background-clip: text;
    background-clip: text;
    -webkit-text-fill-color: transparent;
}

[data-testid="stMarkdownContainer"] p {
    color: #CBD5E1;
}

[data-testid="stAlert"] {
    background: linear-gradient(135deg, rgba(30, 58, 138, 0.22) 0%, rgba(15, 23, 42, 0.65) 100%);
    border: 1px solid rgba(59, 130, 246, 0.28);
    border-radius: 0.75rem;
    box-shadow: 0 0 25px -4px rgba(59, 130, 246, 0.28);
}

[data-testid="stAlert"] p {
    color: #93C5FD !important;
    font-weight: 600;
}

.stButton > button {
    width: 100%;
    background: rgba(30, 41, 59, 0.8);
    color: #CBD5E1;
    border: 1px solid #334155;
    border-radius: 0.6rem;
    font-size: 0.8rem;
    text-align: left;
    padding: 0.55rem 0.9rem;
    transition: all 0.18s ease;
}

.stButton > button:hover {
    background: rgba(51, 65, 85, 0.9);
    color: #FFFFFF;
    border-color: rgba(59, 130, 246, 0.6);
    box-shadow: 0 0 25px -4px rgba(59, 130, 246, 0.28);
    transform: translateY(-1px);
}

[data-testid="stChatMessage"] {
    background: rgba(16, 23, 38, 0.9);
    border: 1px solid rgba(16, 185, 129, 0.25);
    border-radius: 0.85rem;
    padding: 1rem 1.1rem;
    box-shadow: 0 0 25px -4px rgba(16, 185, 129, 0.25);
    backdrop-filter: blur(8px);
}

[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {
    background: #151C2A;
    border-color: rgba(51, 65, 85, 0.6);
    box-shadow: none;
}

[data-testid="stChatMessageAvatarUser"] {
    background: linear-gradient(135deg, #FB7185, #F9A8D4) !important;
    border-radius: 0.75rem !important;
}

[data-testid="stChatMessageAvatarAssistant"] {
    background: rgba(16, 185, 129, 0.15) !important;
    border: 1px solid rgba(16, 185, 129, 0.4) !important;
    border-radius: 0.75rem !important;
    color: #34D399 !important;
}

[data-testid="stChatInput"] {
    background: #141B29;
    border: 1px solid rgba(51, 65, 85, 0.8);
    border-radius: 0.85rem;
}

[data-testid="stChatInput"]:focus-within {
    border-color: #3B82F6;
    box-shadow: 0 0 25px -4px rgba(59, 130, 246, 0.35);
}

[data-testid="stChatInputTextArea"] {
    color: #E2E8F0 !important;
    font-family: 'Plus Jakarta Sans', sans-serif;
}

[data-testid="stChatInputSubmitButton"] {
    background: #334155 !important;
    color: #E2E8F0 !important;
    border-radius: 0.5rem !important;
}

[data-testid="stChatInputSubmitButton"]:hover {
    background: #10B981 !important;
    color: #FFFFFF !important;
    box-shadow: 0 0 25px -4px rgba(16, 185, 129, 0.4);
}

[data-testid="stExpander"] {
    background: rgba(19, 25, 38, 0.7);
    border: 1px solid rgba(51, 65, 85, 0.5);
    border-radius: 0.75rem;
}

[data-testid="stExpander"] summary {
    color: #94A3B8;
}

[data-testid="stCaptionContainer"],
.stCaption {
    color: #64748B !important;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.72rem;
}

[data-testid="stLinkButton"] a {
    background: rgba(59, 130, 246, 0.12);
    color: #93C5FD;
    border: 1px solid rgba(59, 130, 246, 0.25);
    border-radius: 999px;
    padding: 0.3rem 0.75rem;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.72rem;
    text-decoration: none;
}

[data-testid="stLinkButton"] a:hover {
    background: rgba(59, 130, 246, 0.22);
    color: #DBEAFE;
}

[data-testid="stTextInput"] input {
    background: #111724;
    border: 1px solid rgba(51, 65, 85, 0.8);
    border-radius: 0.5rem;
    color: #34D399;
    font-family: 'JetBrains Mono', monospace;
}

[data-testid="stCodeBlock"] code,
[data-testid="stCode"] {
    font-family: 'JetBrains Mono', monospace;
    background: #111724;
    color: #34D399;
}

.groww-subtitle {
    color: #CBD5E1;
    font-size: 0.95rem;
    margin-top: -0.6rem;
    margin-bottom: 0.4rem;
}

.groww-status {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-top: 1.2rem;
    padding-top: 0.9rem;
    border-top: 1px solid rgba(30, 41, 59, 0.8);
    color: #64748B;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.7rem;
}

.groww-status .dot {
    width: 0.5rem;
    height: 0.5rem;
    border-radius: 999px;
    background: #34D399;
    box-shadow: 0 0 10px rgba(16, 185, 129, 0.6);
}

#MainMenu, footer {
    visibility: hidden;
}

[data-testid="stDecoration"] {
    display: none;
}
</style>
"""


def _inject_styles() -> None:
    st.markdown(STYLES, unsafe_allow_html=True)


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

    _inject_styles()

    st.title("Groww MF FAQ Assistant")
    st.markdown(
        '<p class="groww-subtitle">Ask factual questions about the HDFC '
        "mutual fund pages in the knowledge base.</p>",
        unsafe_allow_html=True,
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

    st.sidebar.markdown(
        '<div class="groww-status"><span class="dot"></span>'
        "<span>ChromaDB · fastembed</span></div>",
        unsafe_allow_html=True,
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
