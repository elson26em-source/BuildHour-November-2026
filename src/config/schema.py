from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36 "
    "GrowwMF-FAQ-Demo/1.0"
)

DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_COLLECTION = "groww_mf_faq"
DEFAULT_LLM_MODEL = "qwen/qwen3.8-27b"

SUPPORTED_LLM_PROVIDERS = (
    "groq",
    "gemini",
    "openai",
    "anthropic",
    "mistral",
)

PROVIDER_API_KEY_ENV = {
    "groq": "GROQ_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "mistral": "MISTRAL_API_KEY",
}


@dataclass(frozen=True)
class AppConfig:
    name: str
    disclaimer: str
    max_answer_sentences: int


@dataclass(frozen=True)
class DataConfig:
    source_urls: tuple[str, ...]
    follow_internal_links: bool = False


@dataclass(frozen=True)
class ScrapingConfig:
    timeout_seconds: int = 45
    delay_seconds: float = 1.0
    max_retries: int = 2
    user_agent: str = DEFAULT_USER_AGENT
    use_playwright_fallback: bool = False


@dataclass(frozen=True)
class PathsConfig:
    artifacts_dir: Path
    raw_dir: Path
    html_dir: Path
    manifest_path: Path
    chunks_dir: Path
    embeddings_dir: Path
    retrieval_dir: Path
    answers_dir: Path


@dataclass(frozen=True)
class ChunkingConfig:
    strategy: str = "section_aware"
    max_tokens: int = 450
    overlap_tokens: int = 50


@dataclass(frozen=True)
class EmbeddingConfig:
    model: str = DEFAULT_EMBEDDING_MODEL
    normalize: bool = True
    batch_size: int = 32


@dataclass(frozen=True)
class VectorDBConfig:
    provider: str = "chromadb"
    persist_path: Path = Path("artifacts/03_embeddings/chroma")
    collection: str = DEFAULT_COLLECTION


@dataclass(frozen=True)
class RetrievalConfig:
    top_k: int = 5
    similarity_threshold: float = 0.35


@dataclass(frozen=True)
class LLMConfig:
    provider: str = "groq"
    model: str = DEFAULT_LLM_MODEL
    temperature: float = 0.0
    max_tokens: int = 300
    api_key_env: str = "GROQ_API_KEY"


@dataclass(frozen=True)
class Config:
    app: AppConfig
    data: DataConfig
    scraping: ScrapingConfig
    paths: PathsConfig
    chunking: ChunkingConfig
    embedding: EmbeddingConfig
    vector_db: VectorDBConfig
    retrieval: RetrievalConfig
    llm: LLMConfig
