from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from src.config.loader import load_config
from src.ingestion.chunker import CHUNKS_FILENAME, load_chunks, run_chunking
from src.ingestion.document_loader import Document, DocumentSection
from src.ingestion.embedder import ChunkEmbedder, embed_chunks
from src.ingestion.indexer import IndexingError, index_chunks


class FakeModel:
    def __init__(self, dimension: int = 384) -> None:
        self.dimension = dimension

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
            vector = (
                np.arange(self.dimension, dtype=np.float32)
                + float(len(text) % 23)
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
    )
    vector_db = replace(
        base.vector_db,
        persist_path=tmp_path / "chroma",
    )
    return replace(base, paths=paths, vector_db=vector_db)


def _document() -> Document:
    sections = (
        DocumentSection(
            section="expense_ratio",
            heading="Expense Ratio",
            text="Expense ratio: 1.01%.",
        ),
        DocumentSection(
            section="exit_load",
            heading="Exit Load",
            text="Exit load: 1% within 1 year.",
        ),
        DocumentSection(
            section="benchmark",
            heading="Benchmark",
            text="Benchmark: NIFTY 100 TRI.",
        ),
    )
    return Document(
        doc_id="hdfc-test-fund-direct-growth",
        url="https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
        title="HDFC Test Fund - Groww",
        scheme="HDFC Test Fund",
        page_type="scheme",
        scraped_at="2026-11-09",
        sections=sections,
        faqs=(),
        facts={},
        token_count=sum(len(section.text.split()) for section in sections),
    )


def _prepare(tmp_path: Path):
    config = _config(tmp_path)
    run_chunking(config, documents=[_document()])
    embed_chunks(
        config,
        embedder=ChunkEmbedder("fake-model", model=FakeModel()),
    )
    return config


def test_index_chunks_upserts_metadata_and_is_idempotent(
    tmp_path: Path,
) -> None:
    config = _prepare(tmp_path)
    chunks = load_chunks(config.paths.chunks_dir / CHUNKS_FILENAME)

    result = index_chunks(config)

    assert result.collection_count == result.chunk_count == len(chunks)
    assert result.rebuilt is False
    assert result.sample_source_url in config.data.source_urls

    rerun = index_chunks(config)

    assert rerun.collection_count == len(chunks)

    import chromadb
    from chromadb.config import Settings

    client = chromadb.PersistentClient(
        path=str(config.vector_db.persist_path),
        settings=Settings(anonymized_telemetry=False),
    )
    collection = client.get_collection(config.vector_db.collection)
    stored = collection.get(include=["metadatas", "documents"])

    assert set(stored["ids"]) == {chunk.chunk_id for chunk in chunks}
    assert len(stored["metadatas"]) == len(chunks)
    for metadata in stored["metadatas"]:
        assert set(metadata) == {
            "scheme",
            "section",
            "heading",
            "source_url",
            "scraped_at",
            "doc_id",
        }
        assert metadata["source_url"] in config.data.source_urls
    assert all(document for document in stored["documents"])


def test_index_chunks_rebuild_recreates_collection(tmp_path: Path) -> None:
    config = _prepare(tmp_path)
    chunks = load_chunks(config.paths.chunks_dir / CHUNKS_FILENAME)
    index_chunks(config)

    result = index_chunks(config, rebuild=True)

    assert result.rebuilt is True
    assert result.collection_count == len(chunks)


def test_index_chunks_without_embeddings_raises(tmp_path: Path) -> None:
    config = _config(tmp_path)
    run_chunking(config, documents=[_document()])

    with pytest.raises(IndexingError, match="Embeddings file not found"):
        index_chunks(config)


def test_index_chunks_rejects_count_mismatch(tmp_path: Path) -> None:
    config = _prepare(tmp_path)
    chunks = load_chunks(config.paths.chunks_dir / CHUNKS_FILENAME)
    embeddings = np.zeros((len(chunks) - 1, 384), dtype=np.float32)

    with pytest.raises(IndexingError, match="does not match chunk count"):
        index_chunks(config, embeddings=embeddings)
