from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

from src.guardrails.intent import classify_intent

URL_PATTERN = re.compile(r"https?://[^\s)\]>\"']+")
LAST_UPDATED_PATTERN = re.compile(
    r"Last updated from sources:\s*([^\n]+)",
    re.IGNORECASE,
)
SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")
SOURCE_LINE_PATTERN = re.compile(
    r"^\s*(?:source|last updated from sources)\s*:.*$",
    re.IGNORECASE | re.MULTILINE,
)


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    checks: dict[str, bool]
    errors: tuple[str, ...]
    sentence_count: int
    urls: tuple[str, ...]
    citation_url: str | None
    last_updated: str | None


def strip_urls(text: str) -> str:
    return URL_PATTERN.sub("", text).strip()


def strip_source_lines(text: str) -> str:
    return SOURCE_LINE_PATTERN.sub("", text).strip()


def clean_body(text: str) -> str:
    body = strip_source_lines(strip_urls(text))
    body = re.sub(r"\s+", " ", body).strip()
    return body


def split_sentences(text: str) -> list[str]:
    cleaned = clean_body(text)
    if not cleaned:
        return []
    return [
        sentence.strip()
        for sentence in SENTENCE_BOUNDARY.split(cleaned)
        if sentence.strip()
    ]


def count_sentences(text: str) -> int:
    return len(split_sentences(text))


def truncate_sentences(text: str, *, max_sentences: int = 3) -> str:
    sentences = split_sentences(text)
    if not sentences:
        return ""
    return " ".join(sentences[:max_sentences])


def extract_urls(text: str) -> list[str]:
    return [match.rstrip(".,;:") for match in URL_PATTERN.findall(text)]


def extract_last_updated(text: str) -> str | None:
    match = LAST_UPDATED_PATTERN.search(text)
    if not match:
        return None
    value = match.group(1).strip()
    return value or None


def compose_answer(
    body: str,
    *,
    source_url: str,
    last_updated: str,
) -> str:
    cleaned = truncate_sentences(body)
    if not cleaned:
        cleaned = "Not available from sources."
    return (
        f"{cleaned}\n\n"
        f"Source: {source_url}\n"
        f"Last updated from sources: {last_updated}"
    )


def validate_answer(
    answer: str,
    *,
    allowed_urls: Sequence[str],
    max_sentences: int = 3,
    require_last_updated: bool = True,
) -> ValidationResult:
    sentence_count = count_sentences(answer)
    urls = extract_urls(answer)
    last_updated = extract_last_updated(answer)
    intent = classify_intent(clean_body(answer))

    checks = {
        "sentence_limit": 0 < sentence_count <= max_sentences,
        "single_citation": len(urls) == 1,
        "citation_allowed": len(urls) == 1 and urls[0] in allowed_urls,
        "no_advice_or_performance": intent.intent == "factual",
        "last_updated_present": bool(last_updated),
    }
    if not require_last_updated:
        checks["last_updated_present"] = True

    errors: list[str] = []
    if not checks["sentence_limit"]:
        errors.append(
            f"Answer has {sentence_count} sentences; maximum is "
            f"{max_sentences}."
        )
    if not checks["single_citation"]:
        errors.append(
            f"Answer must contain exactly one URL; found {len(urls)}."
        )
    if not checks["citation_allowed"]:
        errors.append(
            "Citation URL is not in the allowed source list."
        )
    if not checks["no_advice_or_performance"]:
        errors.append(
            "Answer contains advice, comparison, or performance language."
        )
    if not checks["last_updated_present"]:
        errors.append("Answer is missing the last-updated line.")

    return ValidationResult(
        ok=all(checks.values()),
        checks=checks,
        errors=tuple(errors),
        sentence_count=sentence_count,
        urls=tuple(urls),
        citation_url=urls[0] if len(urls) == 1 else None,
        last_updated=last_updated,
    )
