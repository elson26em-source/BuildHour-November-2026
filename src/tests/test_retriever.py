from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from src.config.loader import load_config
from src.ingestion.chunker import run_chunking
from src.ingestion.document_loader import Document, DocumentSection
from src.ingestion.embedder import ChunkEmbedder, embed_chunks
from src.ingestion.indexer import index_chunks
from src.retrieval.retriever import (
    RetrievalError,
    Retriever,
    detect_hints,
)

KEYWORDS = (
    "expense",
    "exit",
    "load",
    "statement",
    "hdfc",
    "large",
    "mid",
    "flexi",
    "elss",
    "benchmark",
    "lock",
    "sip",
    "risk",
)


class KeywordModel:
    dimension = len(KEYWORDS) + 1

    def get_sentence_embedding_dimension(self) -> int:
        return self.dimension

    def encode(
        self,
        texts,
        batch_size: int = 32,
        normalize_embeddings: bool = True,
        show_progress_bar: bool = False,
        convert_to_numpy: bool = True,
    ):
        rows = []
        for text in texts:
            lowered = text.lower()
            vector = np.array(
                [
                    float(lowered.count(keyword))
                    for keyword in KEYWORDS
                ]
                + [0.01],
                dtype=np.float32,
            )
            if normalize_embeddings:
                norm = float(np.linalg.norm(vector))
                if norm:
                    vector = vector / norm
            rows.append(vector)
        return np.vstack(rows).astype(np.float32)


def _config(tmp_path: Path):
    base = load_config(require_api_key=False)
    paths = replace(
        base.paths,
        chunks_dir=tmp_path / "02_chunks",
        embeddings_dir=tmp_path / "03_embeddings",
        retrieval_dir=tmp_path / "04_retrieval",
    )
    vector_db = replace(base.vector_db, persist_path=tmp_path / "chroma")
    return replace(base, paths=paths, vector_db=vector_db)


def _document(
    doc_id: str,
    scheme: str,
    url: str,
    sections: tuple[DocumentSection, ...],
) -> Document:
    return Document(
        doc_id=doc_id,
        url=url,
        title=f"{scheme} - Groww",
        scheme=scheme,
        page_type="scheme",
        scraped_at="2026-11-09",
        sections=sections,
        faqs=(),
        facts={},
        token_count=sum(len(section.text.split()) for section in sections),
    )


def _documents() -> list[Document]:
    return [
        _document(
            "hdfc-large-cap-fund-direct-growth",
            "HDFC Large Cap Fund Direct Growth",
            "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
            (
                DocumentSection(
                    "expense_ratio",
                    "Expense Ratio",
                    "Expense ratio: 1.01%.",
                ),
                DocumentSection(
                    "exit_load",
                    "Exit Load",
                    "Exit load: 1% within 1 year.",
                ),
            ),
        ),
        _document(
            "hdfc-mid-cap-fund-direct-growth",
            "HDFC Mid Cap Fund Direct Growth",
            "https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth",
            (
                DocumentSection(
                    "expense_ratio",
                    "Expense Ratio",
                    "Expense ratio: 0.95%.",
                ),
            ),
        ),
        _document(
            "amc-hdfc-mutual-funds",
            "HDFC Mutual Fund",
            "https://groww.in/mutual-funds/amc/hdfc-mutual-funds",
            (
                DocumentSection(
                    "other",
                    "Statements",
                    "Visit the AMC website to download statements.",
                ),
            ),
        ),
    ]


def _prepare(tmp_path: Path):
    config = _config(tmp_path)
    run_chunking(config, documents=_documents())
    embed_chunks(
        config,
        embedder=ChunkEmbedder("keyword-model", model=KeywordModel()),
    )
    index_chunks(config)
    return config


def _retriever(config) -> Retriever:
    return Retriever(
        config,
        embedder=ChunkEmbedder("keyword-model", model=KeywordModel()),
    )


def test_detect_hints_maps_scheme_and_section() -> None:
    filters = detect_hints(
        "What is the expense ratio of HDFC Large Cap Fund?"
    )

    assert filters.scheme == "HDFC Large Cap Fund Direct Growth"
    assert filters.section == "expense_ratio"


def test_detect_hints_prefers_specific_scheme_over_generic_hdfc() -> None:
    filters = detect_hints("HDFC ELSS lock-in?")

    assert filters.scheme == "HDFC ELSS Tax Saver Fund Direct Plan Growth"
    assert filters.section == "lock_in"


def test_retrieve_applies_scheme_and_section_filters(tmp_path: Path) -> None:
    config = _prepare(tmp_path)

    result = _retriever(config).retrieve(
        "What is the expense ratio of HDFC Large Cap Fund?"
    )

    assert result.filters.scheme == "HDFC Large Cap Fund Direct Growth"
    assert result.filters.section == "expense_ratio"
    assert result.filtered_attempted is True
    assert result.retry_without_filters is False
    assert result.low_confidence is False
    assert result.section_unavailable is False
    assert result.scheme_unavailable is False
    assert result.hits
    assert all(
        hit.scheme == "HDFC Large Cap Fund Direct Growth"
        for hit in result.hits
    )
    assert all(hit.section == "expense_ratio" for hit in result.hits)
    assert result.artifact_path.exists()


def test_retrieve_retries_without_filters_when_empty(tmp_path: Path) -> None:
    config = _prepare(tmp_path)

    result = _retriever(config).retrieve(
        "How can I download my capital-gains statement?"
    )

    assert result.filters.section == "statement_download"
    assert result.filtered_attempted is True
    assert result.retry_without_filters is True
    assert result.section_unavailable is True
    assert result.candidates
    assert result.fallback_source_url in config.data.source_urls


def test_retrieve_marks_low_confidence_below_threshold(
    tmp_path: Path,
) -> None:
    config = _prepare(tmp_path)
    config = replace(
        config,
        retrieval=replace(
            config.retrieval,
            similarity_threshold=1.1,
        ),
    )

    result = _retriever(config).retrieve(
        "What is the expense ratio of HDFC Large Cap Fund?"
    )

    assert result.candidates
    assert result.hits == ()
    assert result.low_confidence is True


def test_retrieve_redacts_pii_in_artifact(tmp_path: Path) -> None:
    config = _prepare(tmp_path)

    result = _retriever(config).retrieve(
        "Expense ratio HDFC Large Cap, email me at test@example.com"
    )

    artifact = json.loads(
        result.artifact_path.read_text(encoding="utf-8")
    )
    assert "test@example.com" not in artifact["query"]
    assert "[REDACTED_EMAIL]" in artifact["query"]
    assert artifact["filters"]["section"] == "expense_ratio"
    assert artifact["hits"]


def test_retrieve_without_collection_raises(tmp_path: Path) -> None:
    config = _config(tmp_path)

    with pytest.raises(RetrievalError, match="was not found"):
        _retriever(config).retrieve("What is the expense ratio?")
