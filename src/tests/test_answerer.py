from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from src.config.loader import load_config
from src.generation.answerer import Answerer
from src.generation.llm_client import LLMError
from src.retrieval.retriever import (
    RetrievalError,
    RetrievalFilters,
    RetrievalHit,
    RetrievalResult,
)

SOURCE_URL = "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth"
EDUCATIONAL_URL = "https://groww.in/mutual-funds/amc/hdfc-mutual-funds"


def _config(tmp_path: Path):
    base = load_config(require_api_key=False)
    paths = replace(
        base.paths,
        retrieval_dir=tmp_path / "04_retrieval",
        answers_dir=tmp_path / "05_answers",
    )
    return replace(base, paths=paths)


def _hit(
    *,
    section: str = "expense_ratio",
    scheme: str = "HDFC Large Cap Fund Direct Growth",
    source_url: str = SOURCE_URL,
) -> RetrievalHit:
    return RetrievalHit(
        chunk_id=f"chunk::{section}::0",
        doc_id="hdfc-large-cap-fund-direct-growth",
        scheme=scheme,
        section=section,
        heading="Expense Ratio",
        text="Expense ratio: 1.01%.",
        source_url=source_url,
        scraped_at="2026-11-09",
        score=0.8,
        distance=0.2,
    )


def _retrieval(
    *,
    hits: tuple[RetrievalHit, ...] | None = None,
    low_confidence: bool = False,
    section_unavailable: bool = False,
    scheme_unavailable: bool = False,
) -> RetrievalResult:
    hit = _hit()
    hits = (_hit(),) if hits is None else hits
    candidates = hits or (_hit(),)
    return RetrievalResult(
        request_id="request-1",
        query="What is the expense ratio?",
        redacted_query="What is the expense ratio?",
        filters=RetrievalFilters(
            scheme="HDFC Large Cap Fund Direct Growth",
            section="expense_ratio",
        ),
        top_k=5,
        similarity_threshold=0.35,
        hits=hits,
        candidates=candidates,
        low_confidence=low_confidence,
        filtered_attempted=True,
        retry_without_filters=False,
        section_unavailable=section_unavailable,
        scheme_unavailable=scheme_unavailable,
        fallback_source_url=candidates[0].source_url,
        collection_name="groww_mf_faq",
        collection_count=51,
        artifact_path=Path("04_retrieval/request-1.json"),
        artifact={"hits": [hit.as_dict()]},
    )


class FakeRetriever:
    def __init__(self, result: RetrievalResult) -> None:
        self.result = result
        self.calls: list[tuple[str, str | None]] = []

    def retrieve(self, query: str, *, request_id: str | None = None):
        self.calls.append((query, request_id))
        return replace(
            self.result,
            request_id=request_id or self.result.request_id,
            query=query,
        )


class FakeLLM:
    def __init__(self, outputs: list[str | Exception]) -> None:
        self.outputs = outputs
        self.calls: list[tuple[str, str]] = []

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((system_prompt, user_prompt))
        output = self.outputs.pop(0)
        if isinstance(output, Exception):
            raise output
        return output


def test_factual_answer_is_composed_and_persisted(tmp_path: Path) -> None:
    config = _config(tmp_path)
    retriever = FakeRetriever(_retrieval())
    llm = FakeLLM(["The expense ratio is 1.01%."])
    answerer = Answerer(config, retriever=retriever, llm_client=llm)

    result = answerer.answer(
        "What is the expense ratio of HDFC Large Cap Fund?",
        request_id="request-1",
    )

    assert result.status == "answered"
    assert result.citation_url == SOURCE_URL
    assert result.last_updated == "2026-11-09"
    assert result.validation is not None
    assert result.validation.ok is True
    assert result.answer.count("http") == 1
    assert "Last updated from sources: 2026-11-09" in result.answer
    assert result.artifact_path is not None
    assert result.artifact_path.exists()
    assert len(llm.calls) == 1


def test_advice_query_is_refused_without_retrieval(tmp_path: Path) -> None:
    config = _config(tmp_path)
    retriever = FakeRetriever(_retrieval())
    llm = FakeLLM(["should not be called"])
    answerer = Answerer(config, retriever=retriever, llm_client=llm)

    result = answerer.answer("Should I invest in HDFC Mid Cap Fund?")

    assert result.status == "refused"
    assert result.intent == "advice"
    assert result.citation_url == EDUCATIONAL_URL
    assert result.answer.count("http") == 1
    assert retriever.calls == []
    assert llm.calls == []


def test_pii_query_is_rejected_and_not_persisted(tmp_path: Path) -> None:
    config = _config(tmp_path)
    retriever = FakeRetriever(_retrieval())
    llm = FakeLLM(["should not be called"])
    answerer = Answerer(config, retriever=retriever, llm_client=llm)

    result = answerer.answer("My PAN is ABCDE1234F")

    assert result.status == "pii"
    assert result.artifact_path is None
    assert result.query == ""
    assert retriever.calls == []
    assert llm.calls == []
    assert not (tmp_path / "05_answers").exists()


def test_low_confidence_returns_source_without_llm(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    retriever = FakeRetriever(
        _retrieval(hits=(), low_confidence=True)
    )
    llm = FakeLLM(["should not be called"])
    answerer = Answerer(config, retriever=retriever, llm_client=llm)

    result = answerer.answer("What is the expense ratio?")

    assert result.status == "low_confidence"
    assert result.validation is not None
    assert result.validation.ok is True
    assert result.citation_url == SOURCE_URL
    assert "not available" in result.answer.lower()
    assert llm.calls == []


def test_low_confidence_without_scheme_links_amc_overview(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    retrieval = replace(
        _retrieval(hits=(), low_confidence=True),
        filters=RetrievalFilters(),
    )
    answerer = Answerer(
        config,
        retriever=FakeRetriever(retrieval),
        llm_client=FakeLLM(["should not be called"]),
    )

    result = answerer.answer("What is the weather today?")

    assert result.status == "low_confidence"
    assert result.citation_url == EDUCATIONAL_URL
    assert result.validation is not None
    assert result.validation.ok is True


def test_section_unavailable_is_reported(tmp_path: Path) -> None:
    config = _config(tmp_path)
    retriever = FakeRetriever(
        _retrieval(
            hits=(_hit(section="other"),),
            section_unavailable=True,
        )
    )
    answerer = Answerer(
        config,
        retriever=retriever,
        llm_client=FakeLLM(["should not be called"]),
    )

    result = answerer.answer(
        "How can I download my capital-gains statement?"
    )

    assert result.status == "section_unavailable"
    assert "section is not available" in result.answer.lower()
    assert result.validation is not None
    assert result.validation.ok is True


def test_invalid_answer_is_retried_with_strict_prompt(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    llm = FakeLLM(
        [
            "You should buy this fund.",
            "The expense ratio is 1.01%.",
        ]
    )
    answerer = Answerer(
        config,
        retriever=FakeRetriever(_retrieval()),
        llm_client=llm,
    )

    result = answerer.answer("What is the expense ratio?")

    assert result.status == "answered"
    assert len(llm.calls) == 2
    assert "previous answer failed validation" in llm.calls[1][0].lower()
    assert result.validation is not None
    assert result.validation.ok is True


def test_invalid_after_retry_falls_back_safely(tmp_path: Path) -> None:
    config = _config(tmp_path)
    llm = FakeLLM(
        [
            "You should buy this fund.",
            "You should sell this fund.",
        ]
    )
    answerer = Answerer(
        config,
        retriever=FakeRetriever(_retrieval()),
        llm_client=llm,
    )

    result = answerer.answer("What is the expense ratio?")

    assert result.status == "error"
    assert "could not produce a verified answer" in result.answer.lower()
    assert result.validation is not None
    assert result.validation.ok is True
    assert result.answer.count("http") == 1


def test_llm_failure_falls_back_safely(tmp_path: Path) -> None:
    config = _config(tmp_path)
    llm = FakeLLM(
        [
            LLMError("rate limited"),
            LLMError("rate limited"),
        ]
    )
    answerer = Answerer(
        config,
        retriever=FakeRetriever(_retrieval()),
        llm_client=llm,
    )

    result = answerer.answer("What is the expense ratio?")

    assert result.status == "error"
    assert len(llm.calls) == 2
    assert "could not produce a verified answer" in result.answer.lower()
    assert result.validation is not None
    assert result.validation.ok is True


def test_empty_index_returns_ingest_message(tmp_path: Path) -> None:
    config = _config(tmp_path)

    class EmptyRetriever:
        def retrieve(self, query: str, *, request_id: str | None = None):
            raise RetrievalError(
                "Chroma collection 'groww_mf_faq' is empty. "
                "Run `python -m src.cli ingest` first."
            )

    answerer = Answerer(
        config,
        retriever=EmptyRetriever(),
        llm_client=FakeLLM(["should not be called"]),
    )

    result = answerer.answer("What is the expense ratio?")

    assert result.status == "error"
    assert "knowledge base is empty" in result.answer.lower()
    assert result.citation_url is None
    assert result.artifact_path is not None
    assert result.artifact_path.exists()
