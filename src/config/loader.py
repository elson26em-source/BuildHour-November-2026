from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dotenv is optional
    load_dotenv = None

from .schema import (
    DEFAULT_COLLECTION,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_LLM_MODEL,
    DEFAULT_USER_AGENT,
    PROVIDER_API_KEY_ENV,
    SUPPORTED_LLM_PROVIDERS,
    AppConfig,
    ChunkingConfig,
    Config,
    DataConfig,
    EmbeddingConfig,
    LLMConfig,
    PathsConfig,
    RetrievalConfig,
    ScrapingConfig,
    VectorDBConfig,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.yaml"
EXPECTED_SOURCE_COUNT = 5
SUPPORTED_VECTOR_DB_PROVIDERS = ("chromadb",)


class ConfigError(ValueError):
    """Raised when config.yaml is missing or invalid."""


def _resolve_path(value: str | Path, base: Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (base / path).resolve()


def _require_mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigError(f"Config section '{name}' must be a mapping.")
    return value


def _require_str(
    section: dict[str, Any],
    key: str,
    section_name: str,
    default: str | None = None,
) -> str:
    value = section.get(key, default)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(
            f"Config value '{section_name}.{key}' is required and must be a "
            "non-empty string."
        )
    return value.strip()


def _require_int(
    section: dict[str, Any],
    key: str,
    section_name: str,
    default: int,
    *,
    minimum: int = 1,
) -> int:
    value = section.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(
            f"Config value '{section_name}.{key}' must be an integer."
        )
    if value < minimum:
        raise ConfigError(
            f"Config value '{section_name}.{key}' must be >= {minimum}."
        )
    return value


def _require_float(
    section: dict[str, Any],
    key: str,
    section_name: str,
    default: float,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    value = section.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(
            f"Config value '{section_name}.{key}' must be a number."
        )
    number = float(value)
    if minimum is not None and number < minimum:
        raise ConfigError(
            f"Config value '{section_name}.{key}' must be >= {minimum}."
        )
    if maximum is not None and number > maximum:
        raise ConfigError(
            f"Config value '{section_name}.{key}' must be <= {maximum}."
        )
    return number


def _require_bool(
    section: dict[str, Any],
    key: str,
    section_name: str,
    default: bool,
) -> bool:
    value = section.get(key, default)
    if not isinstance(value, bool):
        raise ConfigError(
            f"Config value '{section_name}.{key}' must be true or false."
        )
    return value


def _build_config(raw: dict[str, Any], root: Path) -> Config:
    app_raw = _require_mapping(raw.get("app", {}), "app")
    data_raw = _require_mapping(raw.get("data"), "data")
    scraping_raw = _require_mapping(raw.get("scraping", {}), "scraping")
    paths_raw = _require_mapping(raw.get("paths", {}), "paths")
    chunking_raw = _require_mapping(raw.get("chunking", {}), "chunking")
    embedding_raw = _require_mapping(raw.get("embedding", {}), "embedding")
    vector_db_raw = _require_mapping(raw.get("vector_db", {}), "vector_db")
    retrieval_raw = _require_mapping(raw.get("retrieval", {}), "retrieval")
    llm_raw = _require_mapping(raw.get("llm", {}), "llm")

    source_urls = data_raw.get("source_urls")
    if not isinstance(source_urls, list) or not all(
        isinstance(url, str) and url.startswith("https://groww.in/")
        for url in source_urls
    ):
        raise ConfigError(
            "data.source_urls must be a list of https://groww.in/ URLs."
        )
    if len(source_urls) != EXPECTED_SOURCE_COUNT:
        raise ConfigError(
            f"data.source_urls must contain exactly {EXPECTED_SOURCE_COUNT} URLs "
            f"(found {len(source_urls)})."
        )
    if len(set(source_urls)) != len(source_urls):
        raise ConfigError("data.source_urls must not contain duplicate URLs.")

    follow_internal_links = _require_bool(
        data_raw, "follow_internal_links", "data", False
    )
    if follow_internal_links:
        raise ConfigError(
            "data.follow_internal_links must be false; only the five configured "
            "pages may be scraped."
        )

    scraping = ScrapingConfig(
        timeout_seconds=_require_int(
            scraping_raw, "timeout_seconds", "scraping", 45
        ),
        delay_seconds=_require_float(
            scraping_raw, "delay_seconds", "scraping", 1.0, minimum=0.0
        ),
        max_retries=_require_int(
            scraping_raw, "max_retries", "scraping", 2, minimum=0
        ),
        user_agent=_require_str(
            scraping_raw,
            "user_agent",
            "scraping",
            DEFAULT_USER_AGENT,
        ),
        use_playwright_fallback=_require_bool(
            scraping_raw, "use_playwright_fallback", "scraping", False
        ),
    )

    artifacts_dir = _resolve_path(
        paths_raw.get("artifacts_dir", "artifacts"), root
    )
    raw_dir = _resolve_path(
        paths_raw.get("raw_dir", artifacts_dir / "01_raw"), root
    )
    html_dir = _resolve_path(
        paths_raw.get("html_dir", raw_dir / "html"), root
    )
    manifest_path = _resolve_path(
        paths_raw.get("manifest_path", raw_dir / "manifest.json"), root
    )
    chunks_dir = _resolve_path(
        paths_raw.get("chunks_dir", artifacts_dir / "02_chunks"), root
    )
    embeddings_dir = _resolve_path(
        paths_raw.get("embeddings_dir", artifacts_dir / "03_embeddings"), root
    )
    retrieval_dir = _resolve_path(
        paths_raw.get("retrieval_dir", artifacts_dir / "04_retrieval"), root
    )
    answers_dir = _resolve_path(
        paths_raw.get("answers_dir", artifacts_dir / "05_answers"), root
    )

    max_tokens = _require_int(chunking_raw, "max_tokens", "chunking", 450)
    overlap_tokens = _require_int(
        chunking_raw, "overlap_tokens", "chunking", 50, minimum=0
    )
    if overlap_tokens >= max_tokens:
        raise ConfigError(
            "chunking.overlap_tokens must be smaller than chunking.max_tokens."
        )
    chunking = ChunkingConfig(
        strategy=_require_str(
            chunking_raw, "strategy", "chunking", "section_aware"
        ),
        max_tokens=max_tokens,
        overlap_tokens=overlap_tokens,
    )

    embedding = EmbeddingConfig(
        model=_require_str(
            embedding_raw, "model", "embedding", DEFAULT_EMBEDDING_MODEL
        ),
        normalize=_require_bool(embedding_raw, "normalize", "embedding", True),
        batch_size=_require_int(embedding_raw, "batch_size", "embedding", 32),
    )

    db_provider = _require_str(
        vector_db_raw, "provider", "vector_db", "chromadb"
    ).lower()
    if db_provider not in SUPPORTED_VECTOR_DB_PROVIDERS:
        raise ConfigError(
            "vector_db.provider must be one of: "
            f"{', '.join(SUPPORTED_VECTOR_DB_PROVIDERS)}."
        )
    vector_db = VectorDBConfig(
        provider=db_provider,
        persist_path=_resolve_path(
            vector_db_raw.get(
                "persist_path", embeddings_dir / "chroma"
            ),
            root,
        ),
        collection=_require_str(
            vector_db_raw, "collection", "vector_db", DEFAULT_COLLECTION
        ),
    )

    retrieval = RetrievalConfig(
        top_k=_require_int(retrieval_raw, "top_k", "retrieval", 5),
        similarity_threshold=_require_float(
            retrieval_raw,
            "similarity_threshold",
            "retrieval",
            0.35,
            minimum=0.0,
            maximum=1.0,
        ),
    )

    provider = _require_str(llm_raw, "provider", "llm", "groq").lower()
    if provider not in SUPPORTED_LLM_PROVIDERS:
        raise ConfigError(
            "llm.provider must be one of: "
            f"{', '.join(SUPPORTED_LLM_PROVIDERS)}."
        )
    api_key_env = _require_str(
        llm_raw, "api_key_env", "llm", PROVIDER_API_KEY_ENV[provider]
    )
    llm = LLMConfig(
        provider=provider,
        model=_require_str(llm_raw, "model", "llm", DEFAULT_LLM_MODEL),
        temperature=_require_float(
            llm_raw,
            "temperature",
            "llm",
            0.0,
            minimum=0.0,
            maximum=2.0,
        ),
        max_tokens=_require_int(llm_raw, "max_tokens", "llm", 300),
        api_key_env=api_key_env,
    )

    return Config(
        app=AppConfig(
            name=_require_str(
                app_raw, "name", "app", "Groww MF Facts Assistant"
            ),
            disclaimer=_require_str(
                app_raw,
                "disclaimer",
                "app",
                "Facts-only. No investment advice.",
            ),
            max_answer_sentences=_require_int(
                app_raw, "max_answer_sentences", "app", 3
            ),
        ),
        data=DataConfig(
            source_urls=tuple(source_urls),
            follow_internal_links=follow_internal_links,
        ),
        scraping=scraping,
        paths=PathsConfig(
            artifacts_dir=artifacts_dir,
            raw_dir=raw_dir,
            html_dir=html_dir,
            manifest_path=manifest_path,
            chunks_dir=chunks_dir,
            embeddings_dir=embeddings_dir,
            retrieval_dir=retrieval_dir,
            answers_dir=answers_dir,
        ),
        chunking=chunking,
        embedding=embedding,
        vector_db=vector_db,
        retrieval=retrieval,
        llm=llm,
    )


def resolve_api_key(config: Config) -> str | None:
    value = os.environ.get(config.llm.api_key_env, "").strip()
    return value or None


def load_config(
    config_path: str | Path | None = None,
    *,
    project_root: str | Path | None = None,
    require_api_key: bool = True,
) -> Config:
    root = Path(project_root or PROJECT_ROOT).resolve()
    path = Path(config_path) if config_path else root / "config.yaml"

    if not path.exists():
        raise ConfigError(f"Config file not found: {path}")

    if load_dotenv is not None:
        load_dotenv(root / ".env", override=False)

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigError(f"Config root must be a mapping in {path}.")

    config = _build_config(raw, root)

    if require_api_key and resolve_api_key(config) is None:
        raise ConfigError(
            f"Missing API key for LLM provider '{config.llm.provider}': set "
            f"{config.llm.api_key_env} in .env or the environment."
        )

    return config


@lru_cache(maxsize=2)
def get_config(require_api_key: bool = True) -> Config:
    return load_config(require_api_key=require_api_key)
