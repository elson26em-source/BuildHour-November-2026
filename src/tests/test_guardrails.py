from __future__ import annotations

import pytest

from src.guardrails.intent import classify_intent
from src.guardrails.pii import contains_pii, redact_pii
from src.guardrails.templates import (
    DISCLAIMER,
    last_updated_line,
    refusal_message,
)

EDUCATIONAL_URL = "https://groww.in/mutual-funds/amc/hdfc-mutual-funds"


@pytest.mark.parametrize(
    "query",
    [
        "My PAN is ABCDE1234F, check my account",
        "Call me on 9876543210",
        "Email me at test@example.com",
        "Aadhaar 1234 5678 9012",
        "OTP is 4821",
        "Account number 123456789012",
    ],
)
def test_contains_pii_detects_personal_data(query: str) -> None:
    assert contains_pii(query) is True
    redacted = redact_pii(query)
    assert redacted != query
    assert "REDACTED" in redacted


def test_contains_pii_allows_factual_question() -> None:
    assert contains_pii(
        "What is the expense ratio of HDFC Large Cap Fund?"
    ) is False


def test_redact_pii_masks_email_and_pan() -> None:
    redacted = redact_pii("PAN ABCDE1234F and email test@example.com")

    assert "ABCDE1234F" not in redacted
    assert "test@example.com" not in redacted
    assert "[REDACTED_PAN]" in redacted
    assert "[REDACTED_EMAIL]" in redacted


@pytest.mark.parametrize(
    ("query", "intent"),
    [
        ("Should I invest in HDFC Mid Cap Fund?", "advice"),
        ("Which is better, HDFC Flexi Cap or HDFC Large Cap?", "comparison"),
        ("What returns can I expect from ELSS?", "performance"),
        (
            "What is the expense ratio of HDFC Large Cap Fund?",
            "factual",
        ),
        ("How can I download my capital-gains statement?", "factual"),
        ("What is the lock-in period for HDFC ELSS?", "factual"),
    ],
)
def test_classify_intent(query: str, intent: str) -> None:
    assert classify_intent(query).intent == intent


def test_total_return_index_is_not_performance_language() -> None:
    result = classify_intent(
        "Benchmark: NIFTY 500 Total Return Index (NIFTY 500 TRI)."
    )

    assert result.intent == "factual"


def test_refusal_messages_have_one_link() -> None:
    for intent in ("advice", "performance", "comparison"):
        message = refusal_message(intent, url=EDUCATIONAL_URL)
        assert message.count("http") == 1
        assert EDUCATIONAL_URL in message


def test_disclaimer_and_last_updated_line() -> None:
    assert DISCLAIMER == "Facts-only. No investment advice."
    assert last_updated_line("2026-11-09") == (
        "Last updated from sources: 2026-11-09"
    )
