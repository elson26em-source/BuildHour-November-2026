from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from src.config.loader import load_config
from src.evaluation.evaluator import (
    MockLLM,
    evaluate_cases,
    load_eval_cases,
)
from src.generation.answerer import Answerer

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_golden_and_refusal_cases_pass_with_mock_llm(
    tmp_path: Path,
) -> None:
    config = load_config(require_api_key=False)
    if not config.vector_db.persist_path.exists():
        pytest.skip("Chroma index is missing; run ingestion first.")

    paths = replace(
        config.paths,
        retrieval_dir=tmp_path / "04_retrieval",
        answers_dir=tmp_path / "05_answers",
    )
    config = replace(config, paths=paths)

    cases = load_eval_cases(
        PROJECT_ROOT / "eval" / "golden_qa.yaml"
    ) + load_eval_cases(PROJECT_ROOT / "eval" / "refusal_cases.yaml")
    answerer = Answerer(config, llm_client=MockLLM())

    results = evaluate_cases(answerer, cases)
    failures = [
        {
            "case_id": result.case_id,
            "expected": result.expected_status,
            "actual": result.actual_status,
            "failed_checks": [
                name
                for name, ok in result.checks.items()
                if not ok
            ],
        }
        for result in results
        if not result.passed
    ]

    assert not failures, failures
