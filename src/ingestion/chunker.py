from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from src.config.schema import Config
from src.ingestion.document_loader import (
    Document,
    DocumentSection,
    count_tokens,
    load_documents_with_stats,
    required_sections_for,
)

CANONICAL_SECTIONS = (
    "expense_ratio",
    "exit_load",
    "minimum_sip",
    "lock_in",
    "riskometer",
    "benchmark",
    "statement_download",
    "other",
)
CHUNKS_FILENAME = "chunks.jsonl"
STRATEGY_FILENAME = "strategy.md"
CHUNK_FIELDS = (
    "chunk_id",
    "doc_id",
    "scheme",
    "section",
    "heading",
    "text",
    "source_url",
    "scraped_at",
    "token_count",
)

_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")


class ChunkingError(RuntimeError):
    """Raised when documents cannot be converted into valid chunks."""


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    doc_id: str
    scheme: str
    section: str
    heading: str
    text: str
    source_url: str
    scraped_at: str
    token_count: int

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
            "token_count": self.token_count,
        }


@dataclass(frozen=True)
class ChunkStats:
    document_count: int
    section_count: int
    chunk_count: int
    total_tokens: int
    min_chunk_tokens: int
    max_chunk_tokens: int
    sections: tuple[str, ...]


@dataclass(frozen=True)
class ChunkingResult:
    chunks: tuple[Chunk, ...]
    stats: ChunkStats
    warnings: tuple[str, ...]
    chunks_path: Path
    strategy_path: Path
    token_counter_name: str
    report: dict[str, Any]


class TokenCounter:
    """Counts tokens with the embedding tokenizer when available.

    Falls back to whitespace word counting so chunking remains offline and
    deterministic when the model tokenizer is not installed or cached.
    """

    def __init__(
        self,
        model_name: str,
        *,
        prefer_model_tokenizer: bool = True,
    ) -> None:
        self.model_name = model_name
        self.prefer_model_tokenizer = prefer_model_tokenizer
        self._tokenizer: Any | None = None
        self._load_attempted = False
        self._uses_model_tokenizer = False

    def _ensure_tokenizer(self) -> None:
        if self._load_attempted:
            return
        self._load_attempted = True
        if not self.prefer_model_tokenizer:
            return
        try:
            from transformers import AutoTokenizer  # type: ignore[import-not-found]
        except ImportError:
            return
        try:
            self._tokenizer = AutoTokenizer.from_pretrained(
                self.model_name,
                local_files_only=True,
            )
            self._uses_model_tokenizer = True
        except Exception:
            self._tokenizer = None
            self._uses_model_tokenizer = False

    @property
    def name(self) -> str:
        self._ensure_tokenizer()
        if self._uses_model_tokenizer:
            return f"model tokenizer ({self.model_name})"
        return "word-count fallback"

    def count(self, text: str) -> int:
        if not text:
            return 0
        self._ensure_tokenizer()
        if self._tokenizer is not None:
            try:
                return len(
                    self._tokenizer.encode(text, add_special_tokens=False)
                )
            except Exception:
                self._tokenizer = None
                self._uses_model_tokenizer = False
        return count_tokens(text)


def canonical_section(section: str, heading: str = "") -> str:
    key = (section or "").strip().lower()
    if key in CANONICAL_SECTIONS:
        return key

    text = f"{key} {heading}".casefold()
    if "expense" in text:
        return "expense_ratio"
    if "exit load" in text:
        return "exit_load"
    if "minimum sip" in text or "min sip" in text or "min. for sip" in text:
        return "minimum_sip"
    if "lock" in text:
        return "lock_in"
    if "risk" in text:
        return "riskometer"
    if "benchmark" in text:
        return "benchmark"
    if "statement" in text or "capital gain" in text or "download" in text:
        return "statement_download"
    return "other"


def _split_sentences(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []

    units: list[str] = []
    for block in re.split(r"\n+", text):
        block = block.strip()
        if not block:
            continue
        for part in _SENTENCE_BOUNDARY.split(block):
            part = part.strip()
            if part:
                units.append(part)
    return units


def _section_units(section: DocumentSection) -> list[str]:
    prose = section.text or ""
    table_units: list[str] = []
    for table in section.tables:
        for row in table:
            row_text = " | ".join(cell for cell in row if cell)
            if not row_text:
                continue
            if row_text in prose:
                prose = prose.replace(row_text, " ", 1)
            table_units.append(row_text)

    units = _split_sentences(prose)
    units.extend(table_units)
    return [unit for unit in units if unit]


def _split_oversized_unit(
    unit: str,
    max_tokens: int,
    counter: TokenCounter,
) -> list[str]:
    words = unit.split()
    if len(words) <= 1:
        return [unit]

    pieces: list[str] = []
    start = 0
    while start < len(words):
        best = start
        end = start
        while end < len(words):
            candidate = " ".join(words[start : end + 1])
            if counter.count(candidate) > max_tokens:
                break
            best = end + 1
            end += 1
        if best == start:
            best = start + 1
        pieces.append(" ".join(words[start:best]))
        start = best
    return pieces


def _pack_units(
    units: Sequence[str],
    body_max_tokens: int,
    overlap_tokens: int,
    counter: TokenCounter,
) -> list[str]:
    if not units:
        return []

    expanded: list[str] = []
    for unit in units:
        if counter.count(unit) <= body_max_tokens:
            expanded.append(unit)
        else:
            expanded.extend(
                _split_oversized_unit(unit, body_max_tokens, counter)
            )

    chunks: list[str] = []
    current: list[str] = []
    current_tokens = 0

    for unit in expanded:
        unit_tokens = counter.count(unit)
        if current and current_tokens + unit_tokens > body_max_tokens:
            chunks.append(" ".join(current))

            overlap: list[str] = []
            overlap_count = 0
            for previous in reversed(current):
                previous_tokens = counter.count(previous)
                if overlap_count + previous_tokens > overlap_tokens:
                    break
                overlap.insert(0, previous)
                overlap_count += previous_tokens

            while overlap and overlap_count + unit_tokens > body_max_tokens:
                removed = overlap.pop(0)
                overlap_count -= counter.count(removed)

            current = overlap
            current_tokens = overlap_count
            if current_tokens + unit_tokens > body_max_tokens:
                current = []
                current_tokens = 0

        current.append(unit)
        current_tokens += unit_tokens

    if current:
        chunks.append(" ".join(current))
    return chunks


def _prefix_heading(heading: str, body: str) -> str:
    heading = heading.strip()
    body = body.strip()
    if not heading:
        return body
    if body.casefold().startswith(heading.casefold()):
        return body
    return f"{heading}: {body}"


def chunk_document(
    document: Document,
    config: Config,
    *,
    token_counter: TokenCounter | None = None,
) -> tuple[list[Chunk], list[str]]:
    counter = token_counter or TokenCounter(config.embedding.model)
    max_tokens = config.chunking.max_tokens
    overlap_tokens = config.chunking.overlap_tokens

    chunks: list[Chunk] = []
    warnings: list[str] = []
    index_by_section: dict[str, int] = {}

    for section in document.sections:
        section_key = canonical_section(section.section, section.heading)
        heading = section.heading or section_key.replace("_", " ").title()
        units = _section_units(section)
        if not units:
            warnings.append(
                f"{document.doc_id}::{section_key}: skipped empty section."
            )
            continue

        body = " ".join(units)
        full_text = _prefix_heading(heading, body)
        if counter.count(full_text) <= max_tokens:
            bodies = [body]
        else:
            reserved = counter.count(f"{heading}: ")
            body_max = max(1, max_tokens - reserved)
            bodies = _pack_units(
                units,
                body_max,
                overlap_tokens,
                counter,
            )

        for body_text in bodies:
            text = _prefix_heading(heading, body_text)
            token_count = counter.count(text)
            if token_count > max_tokens:
                raise ChunkingError(
                    f"{document.doc_id}::{section_key}: generated a chunk with "
                    f"{token_count} tokens, exceeding max_tokens={max_tokens}."
                )

            index = index_by_section.get(section_key, 0)
            index_by_section[section_key] = index + 1
            chunks.append(
                Chunk(
                    chunk_id=f"{document.doc_id}::{section_key}::{index}",
                    doc_id=document.doc_id,
                    scheme=document.scheme,
                    section=section_key,
                    heading=heading,
                    text=text,
                    source_url=document.url,
                    scraped_at=document.scraped_at,
                    token_count=token_count,
                )
            )

    return chunks, warnings


def _compute_stats(
    documents: Sequence[Document],
    chunks: Sequence[Chunk],
) -> ChunkStats:
    tokens = [chunk.token_count for chunk in chunks]
    return ChunkStats(
        document_count=len(documents),
        section_count=sum(len(document.sections) for document in documents),
        chunk_count=len(chunks),
        total_tokens=sum(tokens),
        min_chunk_tokens=min(tokens) if tokens else 0,
        max_chunk_tokens=max(tokens) if tokens else 0,
        sections=tuple(sorted({chunk.section for chunk in chunks})),
    )


def chunk_documents_with_stats(
    documents: Sequence[Document],
    config: Config,
    *,
    token_counter: TokenCounter | None = None,
) -> ChunkingResult:
    counter = token_counter or TokenCounter(config.embedding.model)
    all_chunks: list[Chunk] = []
    warnings: list[str] = []

    for document in documents:
        document_chunks, document_warnings = chunk_document(
            document,
            config,
            token_counter=counter,
        )
        all_chunks.extend(document_chunks)
        warnings.extend(document_warnings)

    chunk_ids = [chunk.chunk_id for chunk in all_chunks]
    if len(set(chunk_ids)) != len(chunk_ids):
        raise ChunkingError("Generated duplicate chunk IDs.")

    for document in documents:
        required = required_sections_for(document)
        present = {
            chunk.section
            for chunk in all_chunks
            if chunk.doc_id == document.doc_id
        }
        missing = [section for section in required if section not in present]
        if missing:
            warnings.append(
                f"{document.doc_id}: required section(s) produced no chunks: "
                f"{', '.join(missing)}."
            )

    stats = _compute_stats(documents, all_chunks)
    chunks_path = config.paths.chunks_dir / CHUNKS_FILENAME
    strategy_path = config.paths.chunks_dir / STRATEGY_FILENAME
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "strategy": config.chunking.strategy,
        "token_counter": counter.name,
        "max_tokens": config.chunking.max_tokens,
        "overlap_tokens": config.chunking.overlap_tokens,
        "document_count": stats.document_count,
        "section_count": stats.section_count,
        "chunk_count": stats.chunk_count,
        "total_tokens": stats.total_tokens,
        "min_chunk_tokens": stats.min_chunk_tokens,
        "max_chunk_tokens": stats.max_chunk_tokens,
        "sections": list(stats.sections),
        "warnings": warnings,
        "chunks_path": str(chunks_path),
        "strategy_path": str(strategy_path),
    }

    return ChunkingResult(
        chunks=tuple(all_chunks),
        stats=stats,
        warnings=tuple(warnings),
        chunks_path=chunks_path,
        strategy_path=strategy_path,
        token_counter_name=counter.name,
        report=report,
    )


def chunk_documents(
    documents: Sequence[Document],
    config: Config,
    *,
    token_counter: TokenCounter | None = None,
) -> list[Chunk]:
    result = chunk_documents_with_stats(
        documents,
        config,
        token_counter=token_counter,
    )
    return list(result.chunks)


def load_chunks(path: str | Path) -> list[Chunk]:
    chunks_path = Path(path)
    if not chunks_path.exists():
        raise ChunkingError(
            f"Chunks file not found: {chunks_path}. "
            "Run `python -m src.cli chunk` first."
        )

    chunks: list[Chunk] = []
    for line_number, line in enumerate(
        chunks_path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ChunkingError(
                f"Invalid JSON on line {line_number} of {chunks_path}: {exc}"
            ) from exc
        if not isinstance(raw, dict):
            raise ChunkingError(
                f"Line {line_number} of {chunks_path} must be a JSON object."
            )

        missing = [
            field_name
            for field_name in CHUNK_FIELDS
            if field_name not in raw
        ]
        if missing:
            raise ChunkingError(
                f"Line {line_number} of {chunks_path} is missing field(s): "
                f"{', '.join(missing)}."
            )
        empty = [
            field_name
            for field_name in CHUNK_FIELDS
            if field_name != "token_count"
            and not str(raw.get(field_name, "")).strip()
        ]
        if empty:
            raise ChunkingError(
                f"Line {line_number} of {chunks_path} has empty field(s): "
                f"{', '.join(empty)}."
            )

        token_count = raw["token_count"]
        if (
            isinstance(token_count, bool)
            or not isinstance(token_count, int)
            or token_count < 0
        ):
            raise ChunkingError(
                f"Line {line_number} of {chunks_path} has invalid token_count."
            )

        chunks.append(
            Chunk(
                chunk_id=str(raw["chunk_id"]),
                doc_id=str(raw["doc_id"]),
                scheme=str(raw["scheme"]),
                section=str(raw["section"]),
                heading=str(raw["heading"]),
                text=str(raw["text"]),
                source_url=str(raw["source_url"]),
                scraped_at=str(raw["scraped_at"]),
                token_count=token_count,
            )
        )

    chunk_ids = [chunk.chunk_id for chunk in chunks]
    if len(set(chunk_ids)) != len(chunk_ids):
        raise ChunkingError(f"Chunks file {chunks_path} contains duplicate IDs.")
    return chunks


def _write_chunks_jsonl(chunks: Sequence[Chunk], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    with temp_path.open("w", encoding="utf-8", newline="\n") as handle:
        for chunk in chunks:
            handle.write(
                json.dumps(chunk.as_dict(), ensure_ascii=False) + "\n"
            )
    os.replace(temp_path, path)


def _write_strategy_md(result: ChunkingResult, config: Config) -> None:
    stats = result.stats
    lines = [
        "# Chunking Strategy",
        "",
        f"- Strategy: `{config.chunking.strategy}`",
        f"- Token counter: {result.token_counter_name}",
        f"- Max tokens per chunk: {config.chunking.max_tokens}",
        f"- Overlap tokens: {config.chunking.overlap_tokens}",
        f"- Documents: {stats.document_count}",
        f"- Sections: {stats.section_count}",
        f"- Chunks: {stats.chunk_count}",
        f"- Total chunk tokens: {stats.total_tokens}",
        f"- Min chunk tokens: {stats.min_chunk_tokens}",
        f"- Max chunk tokens: {stats.max_chunk_tokens}",
        f"- Canonical sections represented: "
        f"{', '.join(stats.sections) if stats.sections else 'none'}",
        "",
        "## Rules",
        "",
        "- Sections are chunked independently and mapped to canonical "
        "fact types.",
        "- Each chunk text is prefixed with its section heading for context.",
        "- Table rows are kept as atomic units and are not split across "
        "chunks unless a single row exceeds the token limit.",
        "- Long sections are split on sentence boundaries with token overlap.",
        "- Chunk IDs are stable: `<doc_id>::<section>::<index>`.",
        "",
        "## Warnings",
        "",
    ]
    if result.warnings:
        lines.extend(f"- {warning}" for warning in result.warnings)
    else:
        lines.append("- None.")
    lines.append("")

    result.strategy_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = result.strategy_path.with_suffix(
        result.strategy_path.suffix + ".tmp"
    )
    temp_path.write_text("\n".join(lines), encoding="utf-8")
    os.replace(temp_path, result.strategy_path)


def run_chunking(
    config: Config,
    *,
    documents: Sequence[Document] | None = None,
    token_counter: TokenCounter | None = None,
) -> ChunkingResult:
    if documents is None:
        documents = load_documents_with_stats(config).documents

    result = chunk_documents_with_stats(
        documents,
        config,
        token_counter=token_counter,
    )
    _write_chunks_jsonl(result.chunks, result.chunks_path)
    _write_strategy_md(result, config)
    return result
