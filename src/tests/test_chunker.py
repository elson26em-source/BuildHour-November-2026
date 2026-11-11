from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from src.config.loader import load_config
from src.ingestion.chunker import (
    ChunkingError,
    canonical_section,
    chunk_document,
    chunk_documents,
    chunk_documents_with_stats,
    run_chunking,
)
from src.ingestion.document_loader import Document, DocumentSection


def _config(tmp_path: Path, *, max_tokens: int = 50, overlap_tokens: int = 10):
    base = load_config(require_api_key=False)
    chunking = replace(
        base.chunking,
        max_tokens=max_tokens,
        overlap_tokens=overlap_tokens,
    )
    paths = replace(base.paths, chunks_dir=tmp_path / "02_chunks")
    return replace(base, chunking=chunking, paths=paths)


def _document(
    sections: list[DocumentSection],
    *,
    doc_id: str = "hdfc-test-fund-direct-growth",
    scheme: str = "HDFC Test Fund Direct Growth",
    page_type: str = "scheme",
    url: str = "https://groww.in/mutual-funds/hdfc-test-fund-direct-growth",
) -> Document:
    return Document(
        doc_id=doc_id,
        url=url,
        title=f"{scheme} - Groww",
        scheme=scheme,
        page_type=page_type,
        scraped_at="2026-11-09",
        sections=tuple(sections),
        faqs=(),
        facts={},
        token_count=sum(len(section.text.split()) for section in sections),
    )


def _section(
    key: str,
    heading: str,
    text: str,
    tables: tuple[tuple[tuple[str, ...], ...], ...] = (),
) -> DocumentSection:
    return DocumentSection(
        section=key,
        heading=heading,
        text=text,
        tables=tables,
    )


@pytest.mark.parametrize(
    ("section", "heading", "expected"),
    [
        ("expense_ratio", "Expense Ratio", "expense_ratio"),
        ("unknown", "Exit Load", "exit_load"),
        ("minimum_investment", "Minimum Investment", "other"),
        ("unknown", "Minimum SIP amount", "minimum_sip"),
        ("unknown", "Lock-in period", "lock_in"),
        ("unknown", "Riskometer", "riskometer"),
        ("unknown", "Fund benchmark", "benchmark"),
        ("unknown", "Download capital gains statement", "statement_download"),
        ("amc_fund_list", "List of HDFC Mutual Fund in India", "other"),
    ],
)
def test_canonical_section_mapping(
    section: str, heading: str, expected: str
) -> None:
    assert canonical_section(section, heading) == expected


def test_short_section_emits_one_prefixed_chunk(tmp_path: Path) -> None:
    document = _document(
        [
            _section(
                "expense_ratio",
                "Expense Ratio",
                "The total expense ratio is 1.01%.",
            )
        ]
    )

    chunks = chunk_documents([document], _config(tmp_path))

    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.chunk_id == f"{document.doc_id}::expense_ratio::0"
    assert chunk.text == "Expense Ratio: The total expense ratio is 1.01%."
    assert chunk.source_url == document.url
    assert chunk.scraped_at == "2026-11-09"
    assert chunk.token_count >= len(chunk.text.split())


def test_heading_already_in_body_is_not_duplicated(tmp_path: Path) -> None:
    document = _document(
        [
            _section(
                "expense_ratio",
                "Expense Ratio",
                "Expense ratio: 1.01%.",
            )
        ]
    )

    chunks = chunk_documents([document], _config(tmp_path))

    assert chunks[0].text == "Expense ratio: 1.01%."


def test_long_section_splits_with_limit_and_overlap(tmp_path: Path) -> None:
    text = " ".join(
        f"Sentence number {index} has factual content."
        for index in range(100)
    )
    document = _document(
        [_section("other", "Scheme Details", text)]
    )
    config = _config(tmp_path, max_tokens=40, overlap_tokens=20)

    chunks = chunk_documents([document], config)

    assert len(chunks) > 1
    assert all(chunk.token_count <= 40 for chunk in chunks)
    assert len({chunk.chunk_id for chunk in chunks}) == len(chunks)
    assert chunks[0].text.split()[-1] in chunks[1].text


def test_table_rows_are_kept_together(tmp_path: Path) -> None:
    tables = (
        (
            ("Within 1 year", "1%"),
            ("After 1 year", "0%"),
        ),
    )
    document = _document(
        [
            _section(
                "exit_load",
                "Exit Load",
                "Exit load details.",
                tables=tables,
            )
        ]
    )
    config = _config(tmp_path, max_tokens=20, overlap_tokens=5)

    chunks = chunk_documents([document], config)

    assert any("Within 1 year | 1%" in chunk.text for chunk in chunks)
    assert any("After 1 year | 0%" in chunk.text for chunk in chunks)
    assert all(chunk.token_count <= 20 for chunk in chunks)


def test_chunk_ids_are_stable_and_unique(tmp_path: Path) -> None:
    document = _document(
        [
            _section("expense_ratio", "Expense Ratio", "Expense ratio: 1%."),
            _section("expense_ratio", "Expense Ratio", "Expense ratio: 1%."),
            _section("exit_load", "Exit Load", "Exit load: 1%."),
        ]
    )

    first = chunk_documents([document], _config(tmp_path))
    second = chunk_documents([document], _config(tmp_path))

    assert [chunk.chunk_id for chunk in first] == [
        chunk.chunk_id for chunk in second
    ]
    assert len({chunk.chunk_id for chunk in first}) == len(first)
    assert [chunk.chunk_id for chunk in first] == [
        f"{document.doc_id}::expense_ratio::0",
        f"{document.doc_id}::expense_ratio::1",
        f"{document.doc_id}::exit_load::0",
    ]


def test_missing_required_sections_warn(tmp_path: Path) -> None:
    document = _document(
        [_section("expense_ratio", "Expense Ratio", "Expense ratio: 1%.")]
    )

    result = chunk_documents_with_stats(
        [document],
        _config(tmp_path),
    )

    assert any("benchmark" in warning for warning in result.warnings)
    assert any("exit_load" in warning for warning in result.warnings)


def test_run_chunking_writes_jsonl_and_strategy(tmp_path: Path) -> None:
    document = _document(
        [
            _section("expense_ratio", "Expense Ratio", "Expense ratio: 1%."),
            _section("benchmark", "Benchmark", "Benchmark: NIFTY 100 TRI."),
        ]
    )
    config = _config(tmp_path)

    result = run_chunking(config, documents=[document])

    assert result.chunks_path.exists()
    assert result.strategy_path.exists()

    lines = result.chunks_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == result.stats.chunk_count
    first = json.loads(lines[0])
    assert set(first) == {
        "chunk_id",
        "doc_id",
        "scheme",
        "section",
        "heading",
        "text",
        "source_url",
        "scraped_at",
        "token_count",
    }

    strategy = result.strategy_path.read_text(encoding="utf-8")
    assert "section_aware" in strategy
    assert "Max tokens per chunk: 50" in strategy


def test_oversized_section_raises_if_limit_cannot_be_met(tmp_path: Path) -> None:
    document = _document(
        [_section("other", "Details", "supercalifragilisticexpialidocious")]
    )
    config = _config(tmp_path, max_tokens=1, overlap_tokens=0)

    with pytest.raises(ChunkingError, match="exceeding max_tokens"):
        chunk_document(document, config)
