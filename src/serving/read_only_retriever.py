from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from src.config.schema import Config
from src.ingestion.chunker import CHUNKS_FILENAME, Chunk, load_chunks
from src.ingestion.embedder import EMBEDDINGS_FILENAME
from src.retrieval.retriever import RetrievalError, Retriever


@dataclass(frozen=True)
class _ReadOnlyCollection:
    count_value: int

    def count(self) -> int:
        return self.count_value


class ReadOnlyRetriever(Retriever):
    """Serve the prebuilt index from disk without opening a writable database."""

    def __init__(
        self,
        config: Config,
        *,
        embedder: Any,
        index_dir: Path | None = None,
    ) -> None:
        super().__init__(config, embedder=embedder)
        self.index_dir = Path(index_dir or config.vector_db.persist_path)
        try:
            self._chunks: tuple[Chunk, ...] = tuple(
                load_chunks(self.index_dir / CHUNKS_FILENAME)
            )
        except Exception as exc:
            raise RetrievalError(
                f"Could not load chunks from {self.index_dir}: {exc}"
            ) from exc
        try:
            embeddings = np.load(
                self.index_dir / EMBEDDINGS_FILENAME, allow_pickle=False
            )
        except Exception as exc:
            raise RetrievalError(
                f"Could not load embeddings from {self.index_dir}: {exc}"
            ) from exc
        array = np.asarray(embeddings, dtype=np.float32)
        if array.ndim != 2 or array.shape[1] == 0:
            raise RetrievalError(f"Invalid embedding shape: {array.shape}.")
        if array.shape[0] != len(self._chunks):
            raise RetrievalError(
                f"Embedding count {array.shape[0]} does not match "
                f"{len(self._chunks)} chunks."
            )
        self._embeddings = array
        self._collection: Any = None

    def _get_collection(self) -> Any:
        if self._collection is None:
            self._collection = _ReadOnlyCollection(len(self._chunks))
        return self._collection

    def _similarities(self, query_embedding: np.ndarray) -> np.ndarray:
        query = np.asarray(query_embedding, dtype=np.float32)
        if self.config.embedding.normalize:
            return self._embeddings @ query
        query_norm = float(np.linalg.norm(query))
        chunk_norms = np.linalg.norm(self._embeddings, axis=1)
        denominator = np.maximum(chunk_norms * query_norm, 1e-12)
        return (self._embeddings @ query) / denominator

    @staticmethod
    def _conditions(where: dict[str, Any] | None) -> list[dict[str, Any]]:
        if not where:
            return []
        if "$and" in where:
            items = where["$and"]
            return [item for entry in items for item in ReadOnlyRetriever._conditions(entry)]
        return [where]

    def _query(
        self,
        query_embedding: np.ndarray,
        *,
        top_k: int,
        where: dict[str, Any] | None,
    ) -> dict[str, Any]:
        allowed = np.ones(len(self._chunks), dtype=bool)
        for condition in self._conditions(where):
            for field, matcher in condition.items():
                if not isinstance(matcher, dict) or "$eq" not in matcher:
                    raise RetrievalError(
                        f"Unsupported filter on '{field}' in read-only index."
                    )
                expected = str(matcher["$eq"])
                allowed &= np.array(
                    [
                        str(getattr(chunk, field, "")) == expected
                        for chunk in self._chunks
                    ],
                    dtype=bool,
                )

        indices = np.flatnonzero(allowed)
        empty: dict[str, Any] = {"ids": [[]], "metadatas": [[]], "documents": [[]], "distances": [[]]}
        if not len(indices):
            return empty

        similarities = self._similarities(query_embedding)[indices]
        order = np.argsort(-similarities, kind="stable")[:top_k]
        selected = indices[order]
        chosen_similarities = similarities[order]
        return {
            "ids": [[self._chunks[i].chunk_id for i in selected]],
            "metadatas": [
                [
                    {
                        "scheme": self._chunks[i].scheme,
                        "section": self._chunks[i].section,
                        "heading": self._chunks[i].heading,
                        "source_url": self._chunks[i].source_url,
                        "scraped_at": self._chunks[i].scraped_at,
                        "doc_id": self._chunks[i].doc_id,
                    }
                    for i in selected
                ]
            ],
            "documents": [[self._chunks[i].text for i in selected]],
            "distances": [[float(1.0 - value) for value in chosen_similarities]],
        }
