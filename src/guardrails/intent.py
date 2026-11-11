from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IntentResult:
    intent: str
    matched_terms: tuple[str, ...] = ()


COMPARISON_PATTERNS: tuple[str, ...] = (
    "which is better",
    "which fund is better",
    "which one is better",
    "better fund",
    "best fund",
    "compare",
    "comparison",
    " vs ",
    " versus ",
    "outperform",
)

ADVICE_PATTERNS: tuple[str, ...] = (
    "should i",
    "should we",
    "should you",
    "buy this fund",
    "sell this fund",
    "buy or sell",
    "hold this fund",
    "recommend",
    "worth investing",
    "good investment",
    "safe to invest",
    "is it good to invest",
)

PERFORMANCE_PATTERNS: tuple[str, ...] = (
    "returns",
    "cagr",
    "profit",
    "performance",
    "expected return",
    "future return",
    "annualized",
    "how much will i get",
    "how much will we get",
    "return on investment",
    "rate of return",
    "return can i expect",
    "return should i expect",
    "what return",
    "return will i",
)


def classify_intent(query: str) -> IntentResult:
    normalized = f" {query.lower().strip()} "

    for pattern in COMPARISON_PATTERNS:
        if pattern in normalized:
            return IntentResult("comparison", (pattern.strip(),))

    for pattern in ADVICE_PATTERNS:
        if pattern in normalized:
            return IntentResult("advice", (pattern.strip(),))

    for pattern in PERFORMANCE_PATTERNS:
        if pattern in normalized:
            return IntentResult("performance", (pattern.strip(),))

    return IntentResult("factual")
