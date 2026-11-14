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
    background: #F8FAFC;
    color: #0F172A;
}

.stApp::before {
    content: "";
    position: fixed;
    top: -8%;
    right: 8%;
    width: 580px;
    height: 580px;
    background: radial-gradient(circle, rgba(192, 132, 252, 0.30), transparent 70%);
    filter: blur(120px);
    pointer-events: none;
    z-index: 0;
}

.stApp::after {
    content: "";
    position: fixed;
    bottom: -5%;
    left: 12%;
    width: 520px;
    height: 520px;
    background: radial-gradient(circle, rgba(250, 204, 21, 0.26), transparent 70%);
    filter: blur(120px);
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
    font-weight: 700 !important;
    letter-spacing: -0.03em;
    text-align: center;
    background: linear-gradient(90deg, #0F172A 0%, #7E22CE 55%, #D97706 100%);
    -webkit-background-clip: text;
    background-clip: text;
    -webkit-text-fill-color: transparent;
}

[data-testid="stMarkdownContainer"] p {
    color: #1E293B;
}

.growchat-hero {
    text-align: center;
    margin-bottom: 1.1rem;
}

.growchat-badge {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.35rem 0.9rem;
    margin-bottom: 0.7rem;
    border-radius: 999px;
    background: linear-gradient(90deg, #FAF5FF 0%, #FFFFFF 50%, #FFFBEB 100%);
    border: 1px solid rgba(216, 180, 254, 0.7);
    color: #0F172A;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.68rem;
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
}

.growchat-badge .dot {
    width: 0.45rem;
    height: 0.45rem;
    border-radius: 999px;
    background: #F59E0B;
    box-shadow: 0 0 0 3px rgba(245, 158, 11, 0.2);
}

.growchat-subtitle {
    color: #1E293B;
    font-size: 0.95rem;
    font-weight: 500;
    text-align: center;
    max-width: 34rem;
    margin: 0.35rem auto 0 auto;
}

.growchat-suggested {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    margin: 0.2rem 0 0.7rem 0;
    color: #0F172A;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.68rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
}

.growchat-suggested .line {
    height: 1px;
    width: 2rem;
    background: #E2E8F0;
}

[data-testid="stAlert"] {
    background: linear-gradient(90deg, rgba(250, 245, 255, 0.9) 0%, #FFFFFF 50%, rgba(255, 251, 235, 0.9) 100%);
    border: 1px solid rgba(216, 180, 254, 0.7);
    border-radius: 1rem;
    box-shadow: 0 4px 20px -2px rgba(139, 92, 246, 0.10);
}

[data-testid="stAlert"] p {
    color: #6B21A8 !important;
    font-weight: 600;
}

.stButton > button {
    width: 100%;
    background: #FFFFFF;
    color: #0F172A;
    border: 1px solid rgba(216, 180, 254, 0.9);
    border-radius: 999px;
    font-weight: 600;
    font-size: 0.8rem;
    padding: 0.6rem 1rem;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.05);
    transition: all 0.2s ease;
}

.stButton > button::after {
    content: " \\2197";
    color: #CA8A04;
    font-weight: 700;
}

.stButton > button:hover {
    background: #FAF5FF;
    border-color: #C084FC;
    color: #0F172A;
    transform: translateY(-1px);
    box-shadow: 0 4px 16px -2px rgba(168, 85, 247, 0.25);
}

[data-testid="stChatMessage"] {
    position: relative;
    overflow: hidden;
    background: rgba(255, 255, 255, 0.88);
    border: 1px solid rgba(216, 180, 254, 0.6);
    border-radius: 1rem;
    padding: 1rem 1.1rem;
    box-shadow: 0 12px 36px -6px rgba(139, 92, 246, 0.12),
        0 4px 16px -4px rgba(245, 158, 11, 0.08);
    backdrop-filter: blur(14px);
}

[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {
    background: rgba(255, 255, 255, 0.85);
    border-color: rgba(216, 180, 254, 0.55);
    box-shadow: 0 4px 20px -2px rgba(139, 92, 246, 0.08);
}

[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"])::before {
    content: "";
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 4px;
    background: linear-gradient(90deg, #9333EA, #FACC15, #9333EA);
}

[data-testid="stChatMessageAvatarUser"] {
    background: #F3E8FF !important;
    border: 1px solid rgba(216, 180, 254, 0.8) !important;
    border-radius: 0.75rem !important;
    color: #7E22CE !important;
}

[data-testid="stChatMessageAvatarAssistant"] {
    background: linear-gradient(135deg, #4C1D95, #0F172A) !important;
    border: 1px solid rgba(126, 34, 206, 0.4) !important;
    border-radius: 0.75rem !important;
    color: #FACC15 !important;
}

[data-testid="stChatInput"] {
    background: rgba(255, 255, 255, 0.95);
    border: 1px solid rgba(216, 180, 254, 0.8);
    border-radius: 1rem;
    box-shadow: 0 8px 30px -5px rgba(139, 92, 246, 0.12),
        0 4px 12px -2px rgba(245, 158, 11, 0.08);
}

[data-testid="stChatInput"]:focus-within {
    border-color: #FBBF24;
    box-shadow: 0 0 0 3px rgba(250, 204, 21, 0.2);
}

[data-testid="stChatInputTextArea"] {
    color: #0F172A !important;
    font-family: 'Plus Jakarta Sans', sans-serif;
}

[data-testid="stChatInputSubmitButton"] {
    background: linear-gradient(135deg, #7E22CE, #9333EA, #D97706) !important;
    color: #FFFFFF !important;
    border-radius: 0.75rem !important;
}

[data-testid="stChatInputSubmitButton"]:hover {
    background: linear-gradient(135deg, #6B21A8, #7E22CE, #B45309) !important;
    box-shadow: 0 0 18px rgba(168, 85, 247, 0.35);
}

[data-testid="stExpander"] {
    background: rgba(255, 255, 255, 0.85);
    border: 1px solid rgba(216, 180, 254, 0.6);
    border-radius: 0.9rem;
}

[data-testid="stExpander"] summary {
    color: #475569;
}

[data-testid="stCaptionContainer"],
.stCaption {
    color: #64748B !important;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.72rem;
}

[data-testid="stLinkButton"] a {
    background: #FAF5FF;
    color: #6B21A8;
    border: 1px solid rgba(192, 132, 252, 0.5);
    border-radius: 999px;
    padding: 0.3rem 0.8rem;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.72rem;
    text-decoration: none;
}

[data-testid="stLinkButton"] a:hover {
    background: #F3E8FF;
    color: #581C87;
    border-color: #A855F7;
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
        '<div class="growchat-suggested"><span class="line"></span>'
        "Suggested Queries"
        '<span class="line"></span></div>',
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
