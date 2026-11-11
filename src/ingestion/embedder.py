from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np

from src.config.schema import Config
from src.ingestion.chunker import (
    CHUNKS_FILENAME,
    Chunk,
    ChunkingError,
    load_chunks,
)

EMBEDDINGS_FILENAME = "embeddings.npy"
INDEX_MANIFEST_FILENAME = "index_manifest.json"
EXPECTED_DEFAULT_DIMENSION = 384


class EmbeddingError(RuntimeError):
    """Raised when chunk embeddings cannot be generated or saved."""


@dataclass(frozen=True)
class EmbeddingResult:
    embeddings: np.ndarray
    chunk_count: int
    dimension: int
    model_name: str
    normalize: bool
    batch_size: int
    embeddings_path: Path
    manifest_path: Path
    manifest: dict[str, Any]
    warnings: tuple[str, ...] = ()


class ChunkEmbedder:
    """Lazily loads one SentenceTransformer model and reuses it."""

    def __init__(
        self,
        model_name: str,
        *,
        normalize: bool = True,
        batch_size: int = 32,
        model: Any | None = None,
    ) -> None:
        self.model_name = model_name
        self.normalize = normalize
        self.batch_size = max(1, int(batch_size))
        self._model = model
        self._model_loaded = model is not None

    def _ensure_model(self) -> Any:
        if self._model is not None:
            return self._model
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise EmbeddingError(
                "sentence-transformers is not installed. Install project "
                "dependencies with `pip install -r requirements.txt`."
            ) from exc

        try:
            self._model = SentenceTransformer(self.model_name)
        except Exception as exc:
            raise EmbeddingError(
                f"Could not load embedding model '{self.model_name}': {exc}"
            ) from exc
        self._model_loaded = True
        return self._model

    @property
    def model(self) -> Any:
        return self._ensure_model()

    @property
    def dimension(self) -> int | None:
        model = self._ensure_model()
        if hasattr(model, "get_sentence_embedding_dimension"):
            dimension = model.get_sentence_embedding_dimension()
            if dimension is not None:
                return int(dimension)
        if hasattr(model, "dimension"):
            dimension = getattr(model, "dimension")
            if dimension is not None:
                return int(dimension)
        return None

    def _encode_batch(self, batch: Sequence[str]) -> np.ndarray:
        model = self._ensure_model()
        try:
            vectors = model.encode(
                list(batch),
                batch_size=self.batch_size,
                normalize_embeddings=self.normalize,
                show_progress_bar=False,
                convert_to_numpy=True,
            )
        except TypeError:
            vectors = model.encode(list(batch), batch_size=self.batch_size)
        except Exception as exc:
            raise EmbeddingError(
                f"Embedding model '{self.model_name}' failed: {exc}"
            ) from exc

        array = np.asarray(vectors, dtype=np.float32)
        if array.ndim == 1:
            array = array.reshape(1, -1)
        if array.ndim != 2:
            raise EmbeddingError(
                "Embedding model returned an array with an unexpected shape: "
                f"{array.shape}."
            )
        if array.shape[0] != len(batch):
            raise EmbeddingError(
                "Embedding model returned "
                f"{array.shape[0]} vectors for a batch of {len(batch)} texts."
            )
        return array

    def embed_texts(self, texts: Iterable[str]) -> np.ndarray:
        items = list(texts)
        if not items:
            dimension = self.dimension or 0
            return np.empty((0, dimension), dtype=np.float32)

        batches: list[np.ndarray] = []
        for start in range(0, len(items), self.batch_size):
            batch = items[start : start + self.batch_size]
            batches.append(self._encode_batch(batch))
        return np.vstack(batches).astype(np.float32, copy=False)

    def embed_query(self, text: str) -> np.ndarray:
        return self.embed_texts([text])[0]


def _write_npy_atomic(path: Path, embeddings: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(path.name + ".tmp")
    with temp_path.open("wb") as handle:
        np.save(handle, embeddings, allow_pickle=False)
    os.replace(temp_path, path)


def _write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temp_path, path)


def embed_chunks(
    config: Config,
    *,
    chunks: Sequence[Chunk] | None = None,
    embedder: ChunkEmbedder | None = None,
) -> EmbeddingResult:
    chunks_path = config.paths.chunks_dir / CHUNKS_FILENAME
    if chunks is None:
        try:
            chunks = load_chunks(chunks_path)
        except ChunkingError as exc:
            raise EmbeddingError(str(exc)) from exc

    if not chunks:
        raise EmbeddingError(
            f"No chunks found in {chunks_path}. "
            "Run `python -m src.cli chunk` first."
        )

    chunk_embedder = embedder or ChunkEmbedder(
        config.embedding.model,
        normalize=config.embedding.normalize,
        batch_size=config.embedding.batch_size,
    )
    embeddings = chunk_embedder.embed_texts(
        [chunk.text for chunk in chunks]
    )

    if embeddings.shape[0] != len(chunks):
        raise EmbeddingError(
            f"Embedding count {embeddings.shape[0]} does not match chunk "
            f"count {len(chunks)}."
        )
    if embeddings.ndim != 2 or embeddings.shape[1] == 0:
        raise EmbeddingError(
            f"Embeddings have an invalid shape: {embeddings.shape}."
        )

    dimension = int(embeddings.shape[1])
    warnings: list[str] = []
    if dimension != EXPECTED_DEFAULT_DIMENSION:
        warnings.append(
            f"Embedding dimension is {dimension}; the default "
            f"all-MiniLM-L6-v2 model produces {EXPECTED_DEFAULT_DIMENSION}."
        )

    embeddings_path = config.paths.embeddings_dir / EMBEDDINGS_FILENAME
    manifest_path = config.paths.embeddings_dir / INDEX_MANIFEST_FILENAME
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": config.embedding.model,
        "normalize": config.embedding.normalize,
        "batch_size": config.embedding.batch_size,
        "dimension": dimension,
        "chunk_count": len(chunks),
        "embedding_count": int(embeddings.shape[0]),
        "dtype": str(embeddings.dtype),
        "chunks_path": str(chunks_path),
        "embeddings_path": str(embeddings_path),
    }

    _write_npy_atomic(embeddings_path, embeddings)
    _write_json_atomic(manifest_path, manifest)

    return EmbeddingResult(
        embeddings=embeddings,
        chunk_count=len(chunks),
        dimension=dimension,
        model_name=config.embedding.model,
        normalize=config.embedding.normalize,
        batch_size=config.embedding.batch_size,
        embeddings_path=embeddings_path,
        manifest_path=manifest_path,
        manifest=manifest,
        warnings=tuple(warnings),
    )
