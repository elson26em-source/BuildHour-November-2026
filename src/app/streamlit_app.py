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
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=Space+Grotesk:wght@500;600;700&display=swap');

html, body, .stApp, [class*="css"] {
    font-family: 'Plus Jakarta Sans', sans-serif;
}

.stApp {
    background: #FAFAFF;
    color: #1E293B;
}

.stApp::before {
    content: "";
    position: fixed;
    top: 0;
    right: 0;
    width: 50vw;
    height: 60vh;
    background: radial-gradient(ellipse at top right, rgba(233, 213, 255, 0.35) 0%, rgba(243, 232, 255, 0.15) 50%, transparent 75%);
    pointer-events: none;
    z-index: 0;
}

.stApp::after {
    content: "";
    position: fixed;
    bottom: 0;
    left: 0;
    width: 50vw;
    height: 40vh;
    background: radial-gradient(ellipse at bottom left, rgba(254, 240, 138, 0.12) 0%, rgba(253, 230, 138, 0.05) 40%, transparent 70%);
    pointer-events: none;
    z-index: 0;
}

[data-testid="stHeader"] {
    background: transparent;
    border-bottom: none;
}

[data-testid="stAppViewContainer"] > section {
    position: relative;
    z-index: 1;
}

h1 {
    font-family: 'Space Grotesk', sans-serif;
    font-weight: 800 !important;
    letter-spacing: -0.03em;
    text-align: center;
    color: #7E22CE !important;
    -webkit-text-fill-color: #7E22CE;
    background: none;
}

[data-testid="stMarkdownContainer"] p {
    color: #1E293B;
}

.growchat-hero {
    text-align: center;
    margin-bottom: 0.4rem;
}

.growchat-badge {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.28rem 0.75rem;
    border-radius: 999px;
    background: rgba(255, 251, 235, 0.4);
    border: 1px solid rgba(253, 230, 138, 0.8);
    color: #334155;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.66rem;
    font-weight: 500;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
}

.growchat-badge .dot {
    width: 0.45rem;
    height: 0.45rem;
    border-radius: 999px;
    background: #FBBF24;
    display: inline-block;
}

.growchat-subtitle {
    color: #334155;
    font-size: 0.95rem;
    font-weight: 400;
    text-align: center;
    max-width: 34rem;
    margin: 0.2rem auto 0 auto;
}

.growchat-suggested {
    position: relative;
    display: flex;
    align-items: center;
    justify-content: center;
    margin: 0.6rem 0 0.9rem 0;
}

.growchat-suggested::before {
    content: "";
    position: absolute;
    left: 0;
    right: 0;
    top: 50%;
    border-top: 1px solid rgba(226, 232, 240, 0.9);
}

.growchat-suggested span {
    position: relative;
    z-index: 1;
    background: #FAFAFF;
    padding: 0 0.75rem;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.62rem;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    color: #64748B;
}

[data-testid="stAlert"] {
    background: #F6F8FE;
    border: 1px solid #E2E8F8;
    border-radius: 0.5rem;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.02);
    max-width: 42rem;
    margin-left: auto;
    margin-right: auto;
}

[data-testid="stAlert"] [data-testid="stAlertContentInfo"] svg,
[data-testid="stAlert"] [data-testid="stAlertContentWarning"] svg {
    display: none;
}

[data-testid="stAlert"] p {
    color: #553C9A !important;
    font-weight: 500;
    text-align: left;
}

.stButton > button {
    width: 100%;
    background: rgba(255, 255, 255, 0.9);
    color: #334155;
    border: 1px solid rgba(226, 232, 240, 0.8);
    border-radius: 999px;
    font-weight: 500;
    font-size: 0.78rem;
    padding: 0.45rem 0.9rem;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
    transition: all 0.18s ease;
}

.stButton > button::after {
    content: " \\2197";
    color: #F59E0B;
    font-weight: 500;
}

.stButton > button:hover {
    background: #F8FAFC;
    border-color: #CBD5E1;
    color: #0F172A;
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(15, 23, 42, 0.08);
}

[data-testid="stChatMessage"] {
    background: rgba(255, 255, 255, 0.95);
    border: 1px solid rgba(139, 92, 246, 0.4);
    border-radius: 0.75rem;
    padding: 0.9rem 1rem;
    box-shadow: 0 1px 3px rgba(15, 23, 42, 0.05);
}

[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {
    border-color: #F3E8FF;
    align-items: center;
}

[data-testid="stChatMessageAvatarUser"] {
    background: #FAF5FF !important;
    border: 1px solid #F3E8FF !important;
    border-radius: 0.5rem !important;
    color: #8B5CF6 !important;
}

[data-testid="stChatMessageAvatarAssistant"] {
    background: #2E1065 !important;
    border: 1px solid rgba(46, 16, 101, 0.6) !important;
    border-radius: 0.5rem !important;
    color: #FCD34D !important;
}

[data-testid="stChatInput"] {
    background: #FFFFFF;
    border: 1px solid rgba(216, 180, 254, 0.8);
    border-radius: 1rem;
    box-shadow: 0 10px 30px -10px rgba(147, 51, 234, 0.18);
}

[data-testid="stChatInput"]:focus-within {
    border-color: #A855F7;
    box-shadow: 0 0 0 3px rgba(216, 180, 254, 0.35);
}

[data-testid="stChatInputTextArea"] {
    color: #1E293B !important;
    font-family: 'Plus Jakarta Sans', sans-serif;
}

[data-testid="stChatInputSubmitButton"] {
    background: linear-gradient(135deg, #9333EA, #C026D3) !important;
    color: #FFFFFF !important;
    border-radius: 999px !important;
}

[data-testid="stChatInputSubmitButton"]:hover {
    background: linear-gradient(135deg, #7E22CE, #A21CAF) !important;
    box-shadow: 0 0 18px rgba(168, 85, 247, 0.35);
}

[data-testid="stExpander"] {
    background: transparent;
    border: 1px solid rgba(226, 232, 240, 0.7);
    border-radius: 0.5rem;
}

[data-testid="stExpander"] summary {
    color: #94A3B8;
    font-size: 0.78rem;
}

[data-testid="stCaptionContainer"],
.stCaption {
    color: #94A3B8 !important;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.7rem;
}

[data-testid="stLinkButton"] a {
    background: rgba(250, 245, 255, 0.8);
    color: #581C87;
    border: 1px solid rgba(233, 213, 255, 0.9);
    border-radius: 999px;
    padding: 0.25rem 0.75rem;
    font-size: 0.72rem;
    font-weight: 500;
    text-decoration: none;
}

[data-testid="stLinkButton"] a:hover {
    background: #F3E8FF;
    color: #6B21A8;
    border-color: #D8B4FE;
}

[data-testid="stTextInput"] input {
    background: #FFFFFF;
    border: 1px solid rgba(216, 180, 254, 0.8);
    border-radius: 0.6rem;
    color: #6B21A8;
    font-family: 'JetBrains Mono', monospace;
}

[data-testid="stCodeBlock"] code,
[data-testid="stCode"] {
    font-family: 'JetBrains Mono', monospace;
    background: #F8FAFC;
    color: #6B21A8;
}

[data-testid="stSidebar"],
[data-testid="stSidebarContent"] {
    background: #FFFFFF;
    border-right: 1px solid rgba(226, 232, 240, 0.9);
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
        page_title="GrowChat - Mutual Fund FAQ Assistant",
        layout="centered",
        initial_sidebar_state="collapsed",
    )

    _inject_styles()

    st.markdown(
        '<div class="growchat-hero">'
        '<div class="growchat-badge"><span class="dot"></span>'
        "Mutual Fund Intelligence &bull; Facts-Only</div>"
        "</div>",
        unsafe_allow_html=True,
    )
    st.title("GrowChat")
    st.markdown(
        '<p class="growchat-subtitle">Instant factual fund stats, expense '
        "ratios, portfolio compositions, and exit loads.</p>",
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

    if "messages" not in st.session_state:
        st.session_state.messages = []

    st.markdown(
        '<div class="growchat-suggested">'
        "<span>Suggested Queries</span></div>",
        unsafe_allow_html=True,
    )
    columns = st.columns(len(EXAMPLES))
    for column, example in zip(columns, EXAMPLES):
        with column:
            if st.button(example, use_container_width=True):
                _handle_query(answerer, example)

    _render_history()

    prompt = st.chat_input(
        "Ask a factual question about these funds (managers, expense "
        "ratio, exit loads)..."
    )
    if prompt:
        _handle_query(answerer, prompt)


if __name__ == "__main__":
    main()
