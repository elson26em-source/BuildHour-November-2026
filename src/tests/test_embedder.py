from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from src.config.loader import load_config
from src.ingestion.chunker import run_chunking
from src.ingestion.document_loader import Document, DocumentSection
from src.ingestion.embedder import (
    EMBEDDINGS_FILENAME,
    INDEX_MANIFEST_FILENAME,
    ChunkEmbedder,
    EmbeddingError,
    embed_chunks,
)


class FakeModel:
    def __init__(self, dimension: int = 384) -> None:
        self.dimension = dimension
        self.calls: list[list[str]] = []

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
        self.calls.append(list(texts))
        rows = []
        for text in texts:
            vector = (
                np.arange(self.dimension, dtype=np.float32)
                + float(len(text) % 17)
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
    return replace(base, paths=paths)


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
        url="https://groww.in/mutual-funds/hdfc-test-fund-direct-growth",
        title="HDFC Test Fund - Groww",
        scheme="HDFC Test Fund",
        page_type="scheme",
        scraped_at="2026-11-09",
        sections=sections,
        faqs=(),
        facts={},
        token_count=sum(len(section.text.split()) for section in sections),
    )


def test_embed_texts_batches_and_reuses_model() -> None:
    model = FakeModel()
    embedder = ChunkEmbedder("fake-model", batch_size=32, model=model)
    texts = [f"chunk text {index}" for index in range(70)]

    vectors = embedder.embed_texts(texts)

    assert vectors.shape == (70, 384)
    assert [len(call) for call in model.calls] == [32, 32, 6]

    query = embedder.embed_query("expense ratio")

    assert query.shape == (384,)
    assert model.calls[-1] == ["expense ratio"]


def test_embed_query_returns_normalized_vector() -> None:
    model = FakeModel()
    embedder = ChunkEmbedder("fake-model", model=model)

    query = embedder.embed_query("expense ratio")

    assert np.isclose(float(np.linalg.norm(query)), 1.0, atol=1e-5)


def test_embed_chunks_writes_npy_and_manifest(tmp_path: Path) -> None:
    config = _config(tmp_path)
    run_chunking(config, documents=[_document()])
    model = FakeModel()
    embedder = ChunkEmbedder("fake-model", model=model)

    result = embed_chunks(config, embedder=embedder)

    embeddings_path = config.paths.embeddings_dir / EMBEDDINGS_FILENAME
    manifest_path = config.paths.embeddings_dir / INDEX_MANIFEST_FILENAME
    assert result.embeddings_path == embeddings_path
    assert result.manifest_path == manifest_path
    assert embeddings_path.exists()
    assert manifest_path.exists()

    embeddings = np.load(embeddings_path)
    assert embeddings.shape == (result.chunk_count, 384)
    assert result.chunk_count == 3
    assert result.dimension == 384

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["model"] == config.embedding.model
    assert manifest["dimension"] == 384
    assert manifest["chunk_count"] == result.chunk_count
    assert manifest["embedding_count"] == result.chunk_count
    assert manifest["normalize"] == config.embedding.normalize
    assert manifest["generated_at"]


def test_embed_chunks_without_chunks_raises(tmp_path: Path) -> None:
    config = _config(tmp_path)
    embedder = ChunkEmbedder("fake-model", model=FakeModel())

    with pytest.raises(EmbeddingError, match="chunk"):
        embed_chunks(config, embedder=embedder)


def test_non_default_dimension_warns(tmp_path: Path) -> None:
    config = _config(tmp_path)
    run_chunking(config, documents=[_document()])
    embedder = ChunkEmbedder("fake-model", model=FakeModel(dimension=8))

    result = embed_chunks(config, embedder=embedder)

    assert result.dimension == 8
    assert any("384" in warning for warning in result.warnings)
