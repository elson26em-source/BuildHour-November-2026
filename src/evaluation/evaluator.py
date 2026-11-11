from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence
from uuid import uuid4

import yaml

from src.generation.answerer import Answerer
from src.generation.validator import clean_body, count_sentences
from src.guardrails.intent import classify_intent


class EvaluationError(RuntimeError):
    """Raised when evaluation inputs cannot be loaded."""


class MockLLM:
    """Deterministic offline LLM used for evaluation smoke runs."""

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        for line in user_prompt.splitlines():
            if line.startswith("Text: "):
                return line[len("Text: ") :].strip()
        return "The retrieved source contains the requested fact."


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    query: str
    expected_status: tuple[str, ...]
    actual_status: str
    passed: bool
    checks: dict[str, bool]
    answer: str
    citation_url: str | None
    last_updated: str | None
    artifact_path: str | None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_eval_cases(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise EvaluationError(f"Evaluation file not found: {path}")
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise EvaluationError(f"Invalid YAML in {path}: {exc}") from exc
    if not isinstance(payload, list):
        raise EvaluationError(f"Evaluation file must contain a list: {path}")
    cases: list[dict[str, Any]] = []
    for index, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            raise EvaluationError(
                f"Case {index} in {path} must be a mapping."
            )
        for field in ("id", "query", "expected_status"):
            if field not in item:
                raise EvaluationError(
                    f"Case {index} in {path} is missing '{field}'."
                )
        cases.append(item)
    return cases


def _expected_statuses(case: dict[str, Any]) -> tuple[str, ...]:
    expected = case["expected_status"]
    if isinstance(expected, str):
        return (expected,)
    return tuple(expected)


def _check_case(
    case: dict[str, Any],
    result,
    allowed_urls: Sequence[str],
) -> dict[str, bool]:
    checks: dict[str, bool] = {}
    checks["status"] = result.status in _expected_statuses(case)

    expected_citation = case.get("expected_citation", "any")
    if expected_citation == "none":
        checks["citation"] = result.citation_url is None
    elif expected_citation == "educational":
        checks["citation"] = (
            result.citation_url is not None
            and "/amc/" in result.citation_url
        )
    elif expected_citation == "scheme":
        checks["citation"] = (
            result.citation_url is not None
            and result.citation_url in allowed_urls
            and (
                result.retrieval is None
                or not result.retrieval.hits
                or result.citation_url
                == result.retrieval.hits[0].source_url
            )
        )
    else:
        checks["citation"] = (
            result.citation_url is None
            or result.citation_url in allowed_urls
        )

    body = clean_body(result.answer)
    checks["sentence_limit"] = (
        0 < count_sentences(body) <= int(case.get("max_sentences", 3))
    )
    if result.status in {"refused", "pii"}:
        checks["no_advice_or_performance"] = True
    else:
        checks["no_advice_or_performance"] = (
            classify_intent(body).intent == "factual"
        )

    require_last_updated = bool(case.get("require_last_updated", False))
    checks["last_updated"] = (
        bool(result.last_updated) if require_last_updated else True
    )

    expected_intent = case.get("expected_intent")
    if expected_intent:
        checks["intent"] = result.intent == expected_intent

    expected_section = case.get("expected_section")
    if expected_section:
        hits = result.retrieval.hits if result.retrieval else ()
        checks["section"] = any(
            hit.section == expected_section for hit in hits
        )

    expected_scheme = case.get("expected_scheme")
    if expected_scheme:
        hits = result.retrieval.hits if result.retrieval else ()
        checks["scheme"] = any(
            expected_scheme in hit.scheme for hit in hits
        )

    return checks


def evaluate_cases(
    answerer: Answerer,
    cases: Sequence[dict[str, Any]],
) -> list[CaseResult]:
    results: list[CaseResult] = []
    for case in cases:
        result = answerer.answer(
            case["query"],
            request_id=f"eval-{case['id']}-{uuid4().hex[:8]}",
        )
        checks = _check_case(
            case,
            result,
            answerer.config.data.source_urls,
        )
        results.append(
            CaseResult(
                case_id=str(case["id"]),
                query=case["query"],
                expected_status=_expected_statuses(case),
                actual_status=result.status,
                passed=all(checks.values()),
                checks=checks,
                answer=result.answer,
                citation_url=result.citation_url,
                last_updated=result.last_updated,
                artifact_path=(
                    str(result.artifact_path)
                    if result.artifact_path
                    else None
                ),
            )
        )
    return results


def write_report(
    results: Sequence[CaseResult],
    path: Path,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "passed": sum(1 for result in results if result.passed),
        "total": len(results),
        "results": [result.as_dict() for result in results],
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def api_key_available(answerer: Answerer) -> bool:
    return bool(os.environ.get(answerer.config.llm.api_key_env))
