from __future__ import annotations

DISCLAIMER = "Facts-only. No investment advice."

PII_MESSAGE = (
    "I can't process personal information such as PAN, Aadhaar, account "
    "numbers, OTPs, emails, or phone numbers. Please ask a general question "
    "about HDFC mutual fund facts."
)

ADVICE_REFUSAL = (
    "I can only share factual information from the available sources, not "
    "investment advice. For general investor education, see: {url}"
)

PERFORMANCE_REFUSAL = (
    "I can't provide return expectations or performance predictions. For "
    "official scheme facts, see: {url}"
)

COMPARISON_REFUSAL = (
    "I can't compare or rank mutual funds. For factual scheme details, see: "
    "{url}"
)

UNAVAILABLE_MESSAGE = (
    "This information is not available from the scraped sources. Closest "
    "source: {url}"
)

SECTION_UNAVAILABLE_MESSAGE = (
    "This section is not available from the scraped sources for the selected "
    "scheme. Scheme page: {url}"
)

UNAVAILABLE_BODY = (
    "This information is not available from the scraped sources."
)

SECTION_UNAVAILABLE_BODY = (
    "This section is not available from the scraped sources for the selected "
    "scheme."
)

SAFE_FALLBACK_BODY = (
    "I could not produce a verified answer from the sources."
)

EMPTY_INDEX_MESSAGE = (
    "The knowledge base is empty. Run `python -m src.cli ingest` first, then "
    "try again."
)

SAFE_FALLBACK_MESSAGE = (
    "I could not produce a verified answer from the sources. Please check the "
    "scheme page: {url}"
)


def refusal_message(intent: str, *, url: str) -> str:
    if intent == "advice":
        return ADVICE_REFUSAL.format(url=url)
    if intent == "performance":
        return PERFORMANCE_REFUSAL.format(url=url)
    if intent == "comparison":
        return COMPARISON_REFUSAL.format(url=url)
    return UNAVAILABLE_MESSAGE.format(url=url)


def last_updated_line(date: str) -> str:
    return f"Last updated from sources: {date}"
