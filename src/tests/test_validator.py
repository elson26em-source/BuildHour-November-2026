from __future__ import annotations

from src.generation.validator import (
    compose_answer,
    count_sentences,
    extract_last_updated,
    extract_urls,
    truncate_sentences,
    validate_answer,
)

ALLOWED = (
    "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
)
DISALLOWED = "https://example.com/untrusted"


def _valid_answer(body: str = "The expense ratio is 1.01%.") -> str:
    return compose_answer(
        body,
        source_url=ALLOWED[0],
        last_updated="2026-11-09",
    )


def test_valid_answer_passes_all_checks() -> None:
    result = validate_answer(_valid_answer(), allowed_urls=ALLOWED)

    assert result.ok is True
    assert result.sentence_count == 1
    assert result.urls == ALLOWED
    assert result.citation_url == ALLOWED[0]
    assert result.last_updated == "2026-11-09"
    assert all(result.checks.values())


def test_sentence_limit_rejects_long_answer() -> None:
    answer = (
        "One fact. Two facts. Three facts. Four facts.\n\n"
        f"Source: {ALLOWED[0]}\n"
        "Last updated from sources: 2026-11-09"
    )

    result = validate_answer(answer, allowed_urls=ALLOWED)

    assert result.sentence_count == 4
    assert result.checks["sentence_limit"] is False
    assert result.ok is False


def test_citation_must_be_allowlisted() -> None:
    answer = (
        "The expense ratio is 1.01%.\n\n"
        f"Source: {DISALLOWED}\n"
        "Last updated from sources: 2026-11-09"
    )

    result = validate_answer(answer, allowed_urls=ALLOWED)

    assert result.checks["single_citation"] is True
    assert result.checks["citation_allowed"] is False
    assert result.ok is False


def test_multiple_urls_fail_single_citation() -> None:
    answer = (
        f"The expense ratio is 1.01%. See {DISALLOWED}\n\n"
        f"Source: {ALLOWED[0]}\n"
        "Last updated from sources: 2026-11-09"
    )

    result = validate_answer(answer, allowed_urls=ALLOWED)

    assert len(result.urls) == 2
    assert result.checks["single_citation"] is False


def test_advice_language_is_rejected() -> None:
    answer = _valid_answer("You should buy this fund.")

    result = validate_answer(answer, allowed_urls=ALLOWED)

    assert result.checks["no_advice_or_performance"] is False
    assert result.ok is False


def test_missing_last_updated_is_rejected() -> None:
    answer = (
        "The expense ratio is 1.01%.\n\n"
        f"Source: {ALLOWED[0]}"
    )

    result = validate_answer(answer, allowed_urls=ALLOWED)

    assert result.checks["last_updated_present"] is False
    assert result.ok is False


def test_compose_answer_strips_existing_source_and_urls() -> None:
    answer = compose_answer(
        f"The expense ratio is 1.01%. See {DISALLOWED}",
        source_url=ALLOWED[0],
        last_updated="2026-11-09",
    )

    assert DISALLOWED not in answer
    assert answer.count("http") == 1
    assert ALLOWED[0] in answer


def test_truncate_sentences_keeps_first_three() -> None:
    assert truncate_sentences("One. Two. Three. Four.") == (
        "One. Two. Three."
    )


def test_extract_helpers() -> None:
    answer = _valid_answer()

    assert count_sentences(answer) == 1
    assert extract_urls(answer) == [ALLOWED[0]]
    assert extract_last_updated(answer) == "2026-11-09"
