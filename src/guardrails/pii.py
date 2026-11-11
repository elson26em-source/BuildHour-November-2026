from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class PIIPattern:
    name: str
    regex: re.Pattern[str]
    replacement: str


PII_PATTERNS: tuple[PIIPattern, ...] = (
    PIIPattern(
        "pan",
        re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b"),
        "[REDACTED_PAN]",
    ),
    PIIPattern(
        "email",
        re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
        "[REDACTED_EMAIL]",
    ),
    PIIPattern(
        "phone",
        re.compile(r"(?<!\d)(?:\+91[\s-]?)?[6-9]\d{9}(?!\d)"),
        "[REDACTED_PHONE]",
    ),
    PIIPattern(
        "aadhaar",
        re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"),
        "[REDACTED_AADHAAR]",
    ),
    PIIPattern(
        "otp",
        re.compile(
            r"(?i)\b(?:otp|one[\s-]?time\s+password)\b"
            r"[^\d]{0,12}\d{4,8}"
        ),
        "OTP [REDACTED]",
    ),
    PIIPattern(
        "account",
        re.compile(
            r"(?i)\b(?:account|a/c|acct)\s*"
            r"(?:number|no\.?|#)?\s*[:\-]?\s*\d{6,18}\b"
        ),
        "account [REDACTED]",
    ),
)


def contains_pii(text: str) -> bool:
    return any(pattern.regex.search(text) for pattern in PII_PATTERNS)


def redact_pii(text: str) -> str:
    redacted = text
    for pattern in PII_PATTERNS:
        redacted = pattern.regex.sub(pattern.replacement, redacted)
    return redacted
