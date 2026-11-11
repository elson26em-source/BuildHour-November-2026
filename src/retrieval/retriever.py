from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence
from uuid import uuid4

import numpy as np

from src.config.schema import Config
from src.guardrails.pii import redact_pii
from src.ingestion.embedder import ChunkEmbedder


class RetrievalError(RuntimeError):
    """Raised when the vector database cannot be queried."""


SCHEME_HINTS: tuple[tuple[tuple[str, ...], str], ...] = (
    (
        ("large cap", "large-cap", "largecap"),
        "HDFC Large Cap Fund Direct Growth",
    ),
    (
        ("flexi cap", "flexi-cap", "flexicap"),
        "HDFC Flexi Cap Direct Plan Growth",
    ),
    (
        ("elss", "tax saver", "tax-saver", "taxsaver"),
        "HDFC ELSS Tax Saver Fund Direct Plan Growth",
    ),
    (
        ("mid cap", "mid-cap", "midcap"),
        "HDFC Mid Cap Fund Direct Growth",
    ),
    (("hdfc",), "HDFC Mutual Fund"),
)

SECTION_HINTS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("expense ratio", "expense-ratio", "expense ratio"), "expense_ratio"),
    (("exit load", "exit-load", "exitload"), "exit_load"),
    (("minimum sip", "min sip", "minimum-sip"), "minimum_sip"),
    (("lock-in", "lock in", "lockin"), "lock_in"),
    (("riskometer", "risk-o-meter"), "riskometer"),
    (("benchmark",), "benchmark"),
    (
        (
            "statement",
            "capital gain",
            "capital-gain",
            "capital gains",
            "capital-gains",
        ),
        "statement_download",
    ),
)


@dataclass(frozen=True)
class RetrievalFilters:
    scheme: str | None = None
    section: str | None = None

    def as_dict(self) -> dict[str, str | None]:
        return {"scheme": self.scheme, "section": self.section}

    def where(self) -> dict[str, Any] | None:
        conditions: list[dict[str, Any]] = []
        if self.scheme:
            conditions.append({"scheme": {"$eq": self.scheme}})
        if self.section:
            conditions.append({"section": {"$eq": self.section}})
        if not conditions:
            return None
        if len(conditions) == 1:
            return conditions[0]
        return {"$and": conditions}


@dataclass(frozen=True)
class RetrievalHit:
    chunk_id: str
    doc_id: str
    scheme: str
    section: str
    heading: str
    text: str
    source_url: str
    scraped_at: str
    score: float
    distance: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "doc_id": self.doc_id,
            "scheme": self.scheme,
            "section": self.section,
            "heading": self.heading,
            "text": self.text,
            "source_url": self.source_url,
            "scraped_at": self.scraped_at,
            "score": self.score,
            "distance": self.distance,
        }


@dataclass(frozen=True)
class RetrievalResult:
    request_id: str
    query: str
    redacted_query: str
    filters: RetrievalFilters
    top_k: int
    similarity_threshold: float
    hits: tuple[RetrievalHit, ...]
    candidates: tuple[RetrievalHit, ...]
    low_confidence: bool
    filtered_attempted: bool
    retry_without_filters: bool
    section_unavailable: bool
    scheme_unavailable: bool
    fallback_source_url: str | None
    collection_name: str
    collection_count: int
    artifact_path: Path
    artifact: dict[str, Any]


def detect_hints(query: str) -> RetrievalFilters:
    normalized = query.lower()
    scheme: str | None = None
    section: str | None = None

    for patterns, candidate in SCHEME_HINTS:
        if any(pattern in normalized for pattern in patterns):
            scheme = candidate
            break

    for patterns, candidate in SECTION_HINTS:
        if any(pattern in normalized for pattern in patterns):
            section = candidate
            break

    return RetrievalFilters(scheme=scheme, section=section)


def _create_client(persist_path: Path) -> Any:
    try:
        import chromadb
        from chromadb.config import Settings
    except ImportError as exc:
        raise RetrievalError(
            "chromadb is not installed. Install project dependencies with "
            "`pip install -r requirements.txt`."
        ) from exc

    return chromadb.PersistentClient(
        path=str(persist_path),
        settings=Settings(anonymized_telemetry=False),
    )


def _collection_names(client: Any) -> set[str]:
    names: set[str] = set()
    for item in client.list_collections():
        names.add(str(item.name) if hasattr(item, "name") else str(item))
    return names


def _write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temp_path, path)


class Retriever:
    def __init__(
        self,
        config: Config,
        *,
        embedder: Any | None = None,
        client: Any | None = None,
    ) -> None:
        self.config = config
        self.embedder = embedder or ChunkEmbedder(
            config.embedding.model,
            normalize=config.embedding.normalize,
            batch_size=config.embedding.batch_size,
        )
        self._client = client
        self._collection: Any | None = None

    def _get_client(self) -> Any:
        if self._client is None:
            self._client = _create_client(self.config.vector_db.persist_path)
        return self._client

    def _get_collection(self) -> Any:
        if self._collection is not None:
            return self._collection

        client = self._get_client()
        name = self.config.vector_db.collection
        if name not in _collection_names(client):
            raise RetrievalError(
                f"Chroma collection '{name}' was not found at "
                f"{self.config.vector_db.persist_path}. "
                "Run `python -m src.cli ingest` first."
            )
        collection = client.get_collection(name)
        if int(collection.count()) == 0:
            raise RetrievalError(
                f"Chroma collection '{name}' is empty. "
                "Run `python -m src.cli ingest` first."
            )
        self._collection = collection
        return collection

    def _query(
        self,
        query_embedding: np.ndarray,
        *,
        top_k: int,
        where: dict[str, Any] | None,
    ) -> dict[str, Any]:
        collection = self._get_collection()
        kwargs: dict[str, Any] = {
            "query_embeddings": [query_embedding.tolist()],
            "n_results": top_k,
            "include": ["metadatas", "documents", "distances"],
        }
        if where is not None:
            kwargs["where"] = where
        try:
            return collection.query(**kwargs)
        except Exception as exc:
            raise RetrievalError(
                f"Could not query Chroma collection "
                f"'{self.config.vector_db.collection}': {exc}"
            ) from exc

    @staticmethod
    def _hits_from_response(response: dict[str, Any]) -> list[RetrievalHit]:
        ids = response.get("ids") or [[]]
        metadatas = response.get("metadatas") or [[]]
        documents = response.get("documents") or [[]]
        distances = response.get("distances") or [[]]

        if not ids or not ids[0]:
            return []

        hits: list[RetrievalHit] = []
        for index, chunk_id in enumerate(ids[0]):
            metadata = (
                metadatas[0][index]
                if metadatas and metadatas[0] and metadatas[0][index]
                else {}
            )
            text = (
                documents[0][index]
                if documents and documents[0] and documents[0][index]
                else ""
            )
            distance = (
                float(distances[0][index])
                if distances and distances[0] and distances[0][index] is not None
                else 1.0
            )
            hits.append(
                RetrievalHit(
                    chunk_id=str(chunk_id),
                    doc_id=str(metadata.get("doc_id", "")),
                    scheme=str(metadata.get("scheme", "")),
                    section=str(metadata.get("section", "")),
                    heading=str(metadata.get("heading", "")),
                    text=str(text),
                    source_url=str(metadata.get("source_url", "")),
                    scraped_at=str(metadata.get("scraped_at", "")),
                    score=1.0 - distance,
                    distance=distance,
                )
            )
        return hits

    def retrieve(
        self,
        query: str,
        *,
        request_id: str | None = None,
        top_k: int | None = None,
    ) -> RetrievalResult:
        query = query.strip()
        if not query:
            raise RetrievalError("Query must not be empty.")

        request_id = request_id or uuid4().hex
        top_k = top_k or self.config.retrieval.top_k
        if top_k <= 0:
            raise RetrievalError("top_k must be greater than zero.")

        filters = detect_hints(query)
        where = filters.where()
        query_embedding = np.asarray(
            self.embedder.embed_query(query),
            dtype=np.float32,
        )
        if query_embedding.ndim != 1 or query_embedding.size == 0:
            raise RetrievalError("Query embedding has an invalid shape.")

        filtered_attempted = where is not None
        retry_without_filters = False
        response = self._query(query_embedding, top_k=top_k, where=where)
        candidates = self._hits_from_response(response)

        if filtered_attempted and not candidates:
            retry_without_filters = True
            response = self._query(query_embedding, top_k=top_k, where=None)
            candidates = self._hits_from_response(response)

        threshold = self.config.retrieval.similarity_threshold
        hits = tuple(hit for hit in candidates if hit.score >= threshold)
        low_confidence = not hits
        section_unavailable = bool(
            filters.section
            and not any(hit.section == filters.section for hit in hits)
        )
        scheme_unavailable = bool(
            filters.scheme
            and not any(hit.scheme == filters.scheme for hit in hits)
        )
        fallback_source_url = (
            candidates[0].source_url if candidates else None
        )

        collection = self._get_collection()
        redacted_query = redact_pii(query)
        artifact = {
            "request_id": request_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "query": redacted_query,
            "filters": filters.as_dict(),
            "top_k": top_k,
            "similarity_threshold": threshold,
            "filtered_attempted": filtered_attempted,
            "retry_without_filters": retry_without_filters,
            "low_confidence": low_confidence,
            "section_unavailable": section_unavailable,
            "scheme_unavailable": scheme_unavailable,
            "collection": self.config.vector_db.collection,
            "collection_count": int(collection.count()),
            "hits": [hit.as_dict() for hit in hits],
            "candidates": [hit.as_dict() for hit in candidates],
            "fallback_source_url": fallback_source_url,
        }
        artifact_path = (
            self.config.paths.retrieval_dir / f"{request_id}.json"
        )
        _write_json_atomic(artifact_path, artifact)

        return RetrievalResult(
            request_id=request_id,
            query=query,
            redacted_query=redacted_query,
            filters=filters,
            top_k=top_k,
            similarity_threshold=threshold,
            hits=hits,
            candidates=tuple(candidates),
            low_confidence=low_confidence,
            filtered_attempted=filtered_attempted,
            retry_without_filters=retry_without_filters,
            section_unavailable=section_unavailable,
            scheme_unavailable=scheme_unavailable,
            fallback_source_url=fallback_source_url,
            collection_name=self.config.vector_db.collection,
            collection_count=int(collection.count()),
            artifact_path=artifact_path,
            artifact=artifact,
        )
