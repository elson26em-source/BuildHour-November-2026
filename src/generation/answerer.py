from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence
from uuid import uuid4

from src.config.schema import Config
from src.generation.llm_client import LLMError, create_llm_client
from src.generation.prompts import build_system_prompt, build_user_prompt
from src.generation.validator import (
    ValidationResult,
    compose_answer,
    validate_answer,
)
from src.guardrails.intent import IntentResult, classify_intent
from src.guardrails.pii import contains_pii, redact_pii
from src.guardrails.templates import (
    EMPTY_INDEX_MESSAGE,
    PII_MESSAGE,
    SAFE_FALLBACK_BODY,
    SECTION_UNAVAILABLE_BODY,
    UNAVAILABLE_BODY,
    refusal_message,
)
from src.retrieval.retriever import (
    RetrievalError,
    RetrievalHit,
    RetrievalResult,
    Retriever,
)


class AnswerError(RuntimeError):
    """Raised when an answer cannot be produced."""


@dataclass(frozen=True)
class AnswerResult:
    request_id: str
    query: str
    answer: str
    status: str
    intent: str
    citation_url: str | None
    last_updated: str | None
    retrieval: RetrievalResult | None
    validation: ValidationResult | None
    artifact_path: Path | None
    diagnostics: dict[str, Any]


def _write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temp_path, path)


class Answerer:
    def __init__(
        self,
        config: Config,
        *,
        retriever: Any | None = None,
        llm_client: Any | None = None,
    ) -> None:
        self.config = config
        self.retriever = retriever or Retriever(config)
        self._llm_client = llm_client

    def _get_llm(self) -> Any:
        if self._llm_client is None:
            self._llm_client = create_llm_client(self.config)
        return self._llm_client

    def _educational_url(self) -> str:
        for url in self.config.data.source_urls:
            if "/amc/" in url:
                return url
        return self.config.data.source_urls[0]

    def _fallback_source_and_date(
        self,
        retrieval: RetrievalResult,
    ) -> tuple[str, str]:
        candidates: Sequence[RetrievalHit] = (
            retrieval.hits or retrieval.candidates
        )
        if not retrieval.filters.scheme:
            last_updated = (
                candidates[0].scraped_at if candidates else "unknown"
            )
            return self._educational_url(), last_updated
        for hit in candidates:
            if hit.scheme == retrieval.filters.scheme:
                return hit.source_url, hit.scraped_at
        if candidates:
            return candidates[0].source_url, candidates[0].scraped_at
        return self._educational_url(), "unknown"

    def _generate(
        self,
        query: str,
        hits: Sequence[RetrievalHit],
        *,
        strict: bool = False,
        retries: int = 1,
    ) -> tuple[str | None, list[dict[str, Any]]]:
        attempts: list[dict[str, Any]] = []
        for _ in range(retries + 1):
            try:
                llm = self._get_llm()
                output = llm.complete(
                    build_system_prompt(strict=strict),
                    build_user_prompt(query, hits),
                )
            except LLMError as exc:
                attempts.append(
                    {
                        "strict": strict,
                        "output": None,
                        "error": str(exc),
                    }
                )
                continue
            attempts.append(
                {
                    "strict": strict,
                    "output": output,
                    "error": None,
                }
            )
            return output, attempts
        return None, attempts

    def _persist(
        self,
        *,
        request_id: str,
        query: str,
        answer: str,
        status: str,
        intent: str,
        citation_url: str | None,
        last_updated: str | None,
        retrieval: RetrievalResult | None,
        validation: ValidationResult | None,
        llm_attempts: list[dict[str, Any]],
        error: str | None = None,
    ) -> AnswerResult:
        artifact = {
            "request_id": request_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "query": redact_pii(query),
            "status": status,
            "intent": intent,
            "answer": answer,
            "citation_url": citation_url,
            "last_updated": last_updated,
            "retrieval_artifact": (
                str(retrieval.artifact_path) if retrieval else None
            ),
            "retrieval": retrieval.artifact if retrieval else None,
            "validation": asdict(validation) if validation else None,
            "llm_attempts": llm_attempts,
            "error": error,
        }
        artifact_path = (
            self.config.paths.answers_dir / f"{request_id}.json"
        )
        _write_json_atomic(artifact_path, artifact)

        diagnostics = {
            "status": status,
            "intent": intent,
            "filters": retrieval.filters.as_dict() if retrieval else None,
            "low_confidence": (
                retrieval.low_confidence if retrieval else None
            ),
            "section_unavailable": (
                retrieval.section_unavailable if retrieval else None
            ),
            "scheme_unavailable": (
                retrieval.scheme_unavailable if retrieval else None
            ),
            "retrieval_artifact": (
                str(retrieval.artifact_path) if retrieval else None
            ),
            "answer_artifact": str(artifact_path),
            "validation": asdict(validation) if validation else None,
            "llm_attempts": llm_attempts,
            "error": error,
        }
        return AnswerResult(
            request_id=request_id,
            query=query,
            answer=answer,
            status=status,
            intent=intent,
            citation_url=citation_url,
            last_updated=last_updated,
            retrieval=retrieval,
            validation=validation,
            artifact_path=artifact_path,
            diagnostics=diagnostics,
        )

    def answer(
        self,
        query: str,
        *,
        request_id: str | None = None,
    ) -> AnswerResult:
        query = query.strip()
        if not query:
            raise AnswerError("Query must not be empty.")
        request_id = request_id or uuid4().hex

        if contains_pii(query):
            return AnswerResult(
                request_id=request_id,
                query="",
                answer=PII_MESSAGE,
                status="pii",
                intent="pii",
                citation_url=None,
                last_updated=None,
                retrieval=None,
                validation=None,
                artifact_path=None,
                diagnostics={"pii_detected": True},
            )

        intent: IntentResult = classify_intent(query)
        if intent.intent != "factual":
            educational_url = self._educational_url()
            answer = refusal_message(intent.intent, url=educational_url)
            return self._persist(
                request_id=request_id,
                query=query,
                answer=answer,
                status="refused",
                intent=intent.intent,
                citation_url=educational_url,
                last_updated=None,
                retrieval=None,
                validation=None,
                llm_attempts=[],
            )

        try:
            retrieval = self.retriever.retrieve(
                query,
                request_id=request_id,
            )
        except RetrievalError as exc:
            message = str(exc)
            lowered = message.lower()
            if "empty" in lowered or "was not found" in lowered:
                answer = EMPTY_INDEX_MESSAGE
                citation_url = None
                last_updated = None
                validation = None
            else:
                source_url, last_updated = self._educational_url(), "unknown"
                answer = compose_answer(
                    SAFE_FALLBACK_BODY,
                    source_url=source_url,
                    last_updated=last_updated,
                )
                citation_url = source_url
                validation = validate_answer(
                    answer,
                    allowed_urls=self.config.data.source_urls,
                )
            return self._persist(
                request_id=request_id,
                query=query,
                answer=answer,
                status="error",
                intent=intent.intent,
                citation_url=citation_url,
                last_updated=last_updated,
                retrieval=None,
                validation=validation,
                llm_attempts=[],
                error=message,
            )

        if (
            retrieval.low_confidence
            or retrieval.section_unavailable
            or retrieval.scheme_unavailable
        ):
            source_url, last_updated = self._fallback_source_and_date(
                retrieval
            )
            body = (
                SECTION_UNAVAILABLE_BODY
                if retrieval.section_unavailable
                else UNAVAILABLE_BODY
            )
            answer = compose_answer(
                body,
                source_url=source_url,
                last_updated=last_updated,
            )
            validation = validate_answer(
                answer,
                allowed_urls=self.config.data.source_urls,
            )
            status = (
                "section_unavailable"
                if retrieval.section_unavailable
                else "low_confidence"
            )
            return self._persist(
                request_id=request_id,
                query=query,
                answer=answer,
                status=status,
                intent=intent.intent,
                citation_url=source_url,
                last_updated=last_updated,
                retrieval=retrieval,
                validation=validation,
                llm_attempts=[],
            )

        best_hit = retrieval.hits[0]
        body, attempts = self._generate(
            query,
            retrieval.hits,
            strict=False,
            retries=1,
        )
        if body is None:
            answer = compose_answer(
                SAFE_FALLBACK_BODY,
                source_url=best_hit.source_url,
                last_updated=best_hit.scraped_at,
            )
            validation = validate_answer(
                answer,
                allowed_urls=self.config.data.source_urls,
            )
            return self._persist(
                request_id=request_id,
                query=query,
                answer=answer,
                status="error",
                intent=intent.intent,
                citation_url=best_hit.source_url,
                last_updated=best_hit.scraped_at,
                retrieval=retrieval,
                validation=validation,
                llm_attempts=attempts,
                error=attempts[-1]["error"] if attempts else "LLM failed.",
            )

        answer = compose_answer(
            body,
            source_url=best_hit.source_url,
            last_updated=best_hit.scraped_at,
        )
        validation = validate_answer(
            answer,
            allowed_urls=self.config.data.source_urls,
        )

        if not validation.ok:
            strict_body, strict_attempts = self._generate(
                query,
                retrieval.hits,
                strict=True,
                retries=0,
            )
            attempts.extend(strict_attempts)
            if strict_body:
                strict_answer = compose_answer(
                    strict_body,
                    source_url=best_hit.source_url,
                    last_updated=best_hit.scraped_at,
                )
                strict_validation = validate_answer(
                    strict_answer,
                    allowed_urls=self.config.data.source_urls,
                )
                if strict_validation.ok:
                    answer = strict_answer
                    validation = strict_validation

        if not validation.ok:
            answer = compose_answer(
                SAFE_FALLBACK_BODY,
                source_url=best_hit.source_url,
                last_updated=best_hit.scraped_at,
            )
            validation = validate_answer(
                answer,
                allowed_urls=self.config.data.source_urls,
            )
            status = "error"
        else:
            status = "answered"

        return self._persist(
            request_id=request_id,
            query=query,
            answer=answer,
            status=status,
            intent=intent.intent,
            citation_url=best_hit.source_url,
            last_updated=best_hit.scraped_at,
            retrieval=retrieval,
            validation=validation,
            llm_attempts=attempts,
        )
