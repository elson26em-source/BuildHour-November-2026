from __future__ import annotations

import os
import sys
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config.loader import ConfigError, load_config, resolve_api_key
from src.config.schema import normalize_api_key
from src.generation.answerer import AnswerError, Answerer, AnswerResult
from src.generation.validator import clean_body
from src.guardrails.templates import EMPTY_INDEX_MESSAGE
from src.ingestion.embedder import ChunkEmbedder, _FastEmbedAdapter
from src.serving.read_only_retriever import ReadOnlyRetriever

EXAMPLES = (
    "What is the expense ratio of HDFC Large Cap Fund?",
    "What is the lock-in period for HDFC ELSS Tax Saver Fund?",
    "How can I download my capital-gains statement?",
)

INDEX_SOURCE = PROJECT_ROOT / "assets" / "index"
MODEL_SOURCE = PROJECT_ROOT / "assets" / "fastembed" / "all-MiniLM-L6-v2-onnx"
PAGE_PATH = PROJECT_ROOT / "static" / "index.html"

app = FastAPI(title="GrowChat - Mutual Fund FAQ Assistant")

_config: Any = None
_answerer: Answerer | None = None


class AskRequest(BaseModel):
    query: str


def load_runtime_config() -> Any:
    global _config
    if _config is not None:
        return _config

    config = load_config(require_api_key=False)
    runtime_dir = Path(tempfile.mkdtemp(prefix="grow-chat-"))
    if not (INDEX_SOURCE / "embeddings.npy").is_file():
        raise RuntimeError(f"Prebuilt index not found at {INDEX_SOURCE}.")

    _config = replace(
        config,
        vector_db=replace(config.vector_db, persist_path=INDEX_SOURCE),
        paths=replace(
            config.paths,
            retrieval_dir=runtime_dir / "artifacts" / "04_retrieval",
            answers_dir=runtime_dir / "artifacts" / "05_answers",
        ),
    )
    return _config


def get_answerer() -> Answerer:
    global _answerer
    if _answerer is None:
        from fastembed import TextEmbedding

        config = load_runtime_config()
        adapter = _FastEmbedAdapter(
            config.embedding.model,
            TextEmbedding,
            specific_model_path=str(MODEL_SOURCE),
            local_files_only=True,
        )
        embedder = ChunkEmbedder(
            config.embedding.model,
            normalize=config.embedding.normalize,
            batch_size=config.embedding.batch_size,
            model=adapter,
        )
        retriever = ReadOnlyRetriever(config, embedder=embedder, index_dir=INDEX_SOURCE)
        _answerer = Answerer(config, retriever=retriever)
    return _answerer


def serialize_result(result: AnswerResult, display_query: str) -> dict[str, Any]:
    diagnostics = dict(result.diagnostics)
    attempts = diagnostics.get("llm_attempts") or []
    diagnostics["llm_attempts"] = [
        {"strict": attempt.get("strict"), "error": attempt.get("error")}
        for attempt in attempts
    ]

    hits: list[dict[str, Any]] = []
    retrieval = result.retrieval
    if retrieval is not None:
        hits = [
            {
                "chunk_id": hit.chunk_id,
                "scheme": hit.scheme,
                "section": hit.section,
                "score": round(hit.score, 4),
            }
            for hit in (retrieval.hits or retrieval.candidates)
        ]

    empty_index = (
        result.status == "error"
        and result.answer.strip() == EMPTY_INDEX_MESSAGE
    )
    body = result.answer if empty_index else clean_body(result.answer)
    return {
        "request_id": result.request_id,
        "query": display_query,
        "answer": body,
        "empty_index": empty_index,
        "status": result.status,
        "intent": result.intent,
        "citation_url": result.citation_url,
        "last_updated": result.last_updated,
        "diagnostics": diagnostics,
        "hits": hits,
        "retry_without_filters": (
            retrieval.retry_without_filters if retrieval is not None else None
        ),
        "fallback_source_url": (
            retrieval.fallback_source_url if retrieval is not None else None
        ),
    }


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return PAGE_PATH.read_text(encoding="utf-8")


@app.get("/api/config")
def config_info() -> dict[str, Any]:
    config = load_runtime_config()
    return {
        "name": config.app.name,
        "disclaimer": config.app.disclaimer,
        "examples": list(EXAMPLES),
        "api_key_env": config.llm.api_key_env,
        "api_key_configured": resolve_api_key(config) is not None,
        "empty_index_message": EMPTY_INDEX_MESSAGE,
    }


@app.get("/api/health")
def health() -> dict[str, Any]:
    config = load_runtime_config()
    return {
        "provider": config.llm.provider,
        "model": config.llm.model,
        "groq_api_key_present": (
            normalize_api_key(os.environ.get("GROQ_API_KEY"), "GROQ_API_KEY")
            is not None
        ),
    }


@app.post("/api/ask")
def ask(payload: AskRequest) -> dict[str, Any]:
    query = payload.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query must not be empty.")
    try:
        result = get_answerer().answer(query)
    except AnswerError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ConfigError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    display_query = (
        "[Personal information removed]" if result.status == "pii" else query
    )
    return serialize_result(result, display_query)
