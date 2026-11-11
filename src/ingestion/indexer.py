from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from src.config.schema import Config
from src.ingestion.chunker import (
    CHUNKS_FILENAME,
    Chunk,
    ChunkingError,
    load_chunks,
)
from src.ingestion.embedder import (
    EMBEDDINGS_FILENAME,
    INDEX_MANIFEST_FILENAME,
)

INDEX_BATCH_SIZE = 100


class IndexingError(RuntimeError):
    """Raised when chunks cannot be stored in the vector database."""


@dataclass(frozen=True)
class IndexResult:
    collection_name: str
    collection_count: int
    chunk_count: int
    persist_path: Path
    rebuilt: bool
    chunks_path: Path
    embeddings_path: Path
    manifest_path: Path
    sample_chunk_id: str
    sample_source_url: str
    warnings: tuple[str, ...] = ()


def _load_embeddings(path: Path) -> np.ndarray:
    if not path.exists():
        raise IndexingError(
            f"Embeddings file not found: {path}. "
            "Run `python -m src.cli embed` first."
        )
    try:
        embeddings = np.load(path, allow_pickle=False)
    except Exception as exc:
        raise IndexingError(f"Could not read embeddings from {path}: {exc}") from exc

    array = np.asarray(embeddings, dtype=np.float32)
    if array.ndim != 2 or array.shape[1] == 0:
        raise IndexingError(
            f"Embeddings in {path} have an invalid shape: {array.shape}."
        )
    return array


def _load_manifest(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise IndexingError(
            f"Could not read embedding manifest {path}: {exc}"
        ) from exc
    if not isinstance(raw, dict):
        raise IndexingError(f"Embedding manifest {path} must be a JSON object.")
    return raw


def _validate_manifest(
    manifest: dict[str, Any] | None,
    *,
    config: Config,
    chunks: Sequence[Chunk],
    embeddings: np.ndarray,
    manifest_path: Path,
) -> None:
    if manifest is None:
        return

    if manifest.get("model") != config.embedding.model:
        raise IndexingError(
            f"Embedding manifest model {manifest.get('model')!r} does not "
            f"match config model {config.embedding.model!r}. "
            "Re-run `python -m src.cli embed`."
        )
    if int(manifest.get("dimension", -1)) != int(embeddings.shape[1]):
        raise IndexingError(
            f"Embedding manifest dimension {manifest.get('dimension')!r} "
            f"does not match embeddings shape {embeddings.shape}."
        )
    if int(manifest.get("chunk_count", -1)) != len(chunks):
        raise IndexingError(
            f"Embedding manifest chunk_count {manifest.get('chunk_count')!r} "
            f"does not match {len(chunks)} chunks. "
            "Re-run `python -m src.cli embed`."
        )
    if manifest_path.stat().st_size == 0:
        raise IndexingError(f"Embedding manifest {manifest_path} is empty.")


def _create_client(persist_path: Path) -> Any:
    try:
        import chromadb
        from chromadb.config import Settings
    except ImportError as exc:
        raise IndexingError(
            "chromadb is not installed. Install project dependencies with "
            "`pip install -r requirements.txt`."
        ) from exc

    persist_path.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(
        path=str(persist_path),
        settings=Settings(anonymized_telemetry=False),
    )


def _collection_name(item: Any) -> str:
    if hasattr(item, "name"):
        return str(item.name)
    return str(item)


def _metadata_for_chunk(chunk: Chunk) -> dict[str, str]:
    return {
        "scheme": chunk.scheme,
        "section": chunk.section,
        "heading": chunk.heading,
        "source_url": chunk.source_url,
        "scraped_at": chunk.scraped_at,
        "doc_id": chunk.doc_id,
    }


def _verify_sample_query(
    collection: Any,
    embeddings: np.ndarray,
    chunks: Sequence[Chunk],
    allowed_urls: Sequence[str],
) -> tuple[str, str]:
    result = collection.query(
        query_embeddings=[embeddings[0].tolist()],
        n_results=1,
        include=["metadatas", "documents"],
    )
    ids = result.get("ids") or [[]]
    metadatas = result.get("metadatas") or [[]]
    if not ids or not ids[0]:
        raise IndexingError(
            f"Sample query returned no results from collection "
            f"'{collection.name}'."
        )

    metadata = metadatas[0][0] if metadatas and metadatas[0] else {}
    source_url = str(metadata.get("source_url", ""))
    if source_url not in allowed_urls:
        raise IndexingError(
            "Sample query returned a chunk with a source URL outside the "
            f"configured allowlist: {source_url!r}."
        )
    chunk_ids = {chunk.chunk_id for chunk in chunks}
    if str(ids[0][0]) not in chunk_ids:
        raise IndexingError(
            f"Sample query returned an unknown chunk ID: {ids[0][0]!r}."
        )
    return str(ids[0][0]), source_url


def index_chunks(
    config: Config,
    *,
    rebuild: bool = False,
    chunks: Sequence[Chunk] | None = None,
    embeddings: np.ndarray | None = None,
    client: Any | None = None,
) -> IndexResult:
    chunks_path = config.paths.chunks_dir / CHUNKS_FILENAME
    embeddings_path = config.paths.embeddings_dir / EMBEDDINGS_FILENAME
    manifest_path = config.paths.embeddings_dir / INDEX_MANIFEST_FILENAME

    if chunks is None:
        try:
            chunks = load_chunks(chunks_path)
        except ChunkingError as exc:
            raise IndexingError(str(exc)) from exc
    if not chunks:
        raise IndexingError(
            f"No chunks found in {chunks_path}. "
            "Run `python -m src.cli chunk` first."
        )

    if embeddings is None:
        embeddings = _load_embeddings(embeddings_path)
    else:
        embeddings = np.asarray(embeddings, dtype=np.float32)
        if embeddings.ndim != 2 or embeddings.shape[1] == 0:
            raise IndexingError(
                f"Embeddings have an invalid shape: {embeddings.shape}."
            )

    if embeddings.shape[0] != len(chunks):
        raise IndexingError(
            f"Embedding count {embeddings.shape[0]} does not match chunk "
            f"count {len(chunks)}."
        )

    manifest = _load_manifest(manifest_path)
    _validate_manifest(
        manifest,
        config=config,
        chunks=chunks,
        embeddings=embeddings,
        manifest_path=manifest_path,
    )
    warnings: list[str] = []
    if manifest is None:
        warnings.append(
            f"Embedding manifest not found at {manifest_path}; "
            "indexing using the supplied embeddings."
        )

    chroma_client = (
        client
        if client is not None
        else _create_client(config.vector_db.persist_path)
    )
    collection_name = config.vector_db.collection
    existing_names = {
        _collection_name(item)
        for item in chroma_client.list_collections()
    }

    rebuilt = False
    if rebuild and collection_name in existing_names:
        chroma_client.delete_collection(collection_name)
        rebuilt = True

    collection = chroma_client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )

    for start in range(0, len(chunks), INDEX_BATCH_SIZE):
        end = start + INDEX_BATCH_SIZE
        batch = chunks[start:end]
        collection.upsert(
            ids=[chunk.chunk_id for chunk in batch],
            embeddings=embeddings[start:end].tolist(),
            documents=[chunk.text for chunk in batch],
            metadatas=[_metadata_for_chunk(chunk) for chunk in batch],
        )

    collection_count = int(collection.count())
    if collection_count != len(chunks):
        raise IndexingError(
            f"Collection '{collection_name}' has {collection_count} records "
            f"but {len(chunks)} chunks were indexed. Re-run with --rebuild "
            "to remove stale records."
        )

    sample_chunk_id, sample_source_url = _verify_sample_query(
        collection,
        embeddings,
        chunks,
        config.data.source_urls,
    )

    return IndexResult(
        collection_name=collection_name,
        collection_count=collection_count,
        chunk_count=len(chunks),
        persist_path=config.vector_db.persist_path,
        rebuilt=rebuilt,
        chunks_path=chunks_path,
        embeddings_path=embeddings_path,
        manifest_path=manifest_path,
        sample_chunk_id=sample_chunk_id,
        sample_source_url=sample_source_url,
        warnings=tuple(warnings),
    )
