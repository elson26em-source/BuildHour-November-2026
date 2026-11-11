from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from html import unescape
from pathlib import Path
from typing import Any

from src.config.schema import Config
from src.ingestion.loader import (
    map_heading_to_section,
    page_type_from_url,
    slug_from_url,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST_PATH = PROJECT_ROOT / "artifacts/01_raw/manifest.json"
LOAD_REPORT_NAME = "load_report.json"

REQUIRED_DOCUMENT_FIELDS = (
    "doc_id",
    "url",
    "title",
    "scheme",
    "scraped_at",
    "sections",
)
REQUIRED_FACT_SECTIONS = (
    "expense_ratio",
    "exit_load",
    "minimum_sip",
    "riskometer",
    "benchmark",
)
ELSS_REQUIRED_FACT_SECTIONS = ("lock_in",)

_ZERO_WIDTH_TABLE = {
    ord(character): None
    for character in "\u200b\u200c\u200d\u2060\ufeff"
}


class DocumentLoadError(RuntimeError):
    """Raised when raw documents cannot be loaded or validated."""


@dataclass(frozen=True)
class FAQ:
    question: str
    answer: str


@dataclass(frozen=True)
class DocumentSection:
    section: str
    heading: str
    text: str
    tables: tuple[tuple[tuple[str, ...], ...], ...] = ()


@dataclass(frozen=True)
class Document:
    doc_id: str
    url: str
    title: str
    scheme: str
    page_type: str
    scraped_at: str
    sections: tuple[DocumentSection, ...]
    faqs: tuple[FAQ, ...]
    facts: dict[str, Any]
    token_count: int
    warnings: tuple[str, ...] = ()

    @property
    def section_keys(self) -> tuple[str, ...]:
        return tuple(section.section for section in self.sections)

    def as_dict(self) -> dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "url": self.url,
            "title": self.title,
            "scheme": self.scheme,
            "page_type": self.page_type,
            "scraped_at": self.scraped_at,
            "sections": [
                {
                    "section": section.section,
                    "heading": section.heading,
                    "text": section.text,
                    "tables": [
                        [list(row) for row in table]
                        for table in section.tables
                    ],
                }
                for section in self.sections
            ],
            "faqs": [
                {"question": faq.question, "answer": faq.answer}
                for faq in self.faqs
            ],
            "facts": self.facts,
            "token_count": self.token_count,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class LoadStats:
    document_count: int
    section_count: int
    total_tokens: int


@dataclass(frozen=True)
class LoadResult:
    documents: tuple[Document, ...]
    stats: LoadStats
    report: dict[str, Any]
    report_path: Path
    warnings: tuple[str, ...] = field(default_factory=tuple)


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    text = unescape(str(value))
    text = text.translate(_ZERO_WIDTH_TABLE).replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def count_tokens(text: str) -> int:
    """Word-count fallback used for load statistics.

    The chunker later uses the embedding tokenizer when available.
    """
    return len(text.split())


def _normalize_tables(value: Any) -> tuple[tuple[tuple[str, ...], ...], ...]:
    if not isinstance(value, list):
        return ()
    tables: list[tuple[tuple[str, ...], ...]] = []
    for raw_table in value:
        if not isinstance(raw_table, list):
            continue
        rows: list[tuple[str, ...]] = []
        for raw_row in raw_table:
            if not isinstance(raw_row, list):
                continue
            cells = tuple(normalize_text(cell) for cell in raw_row)
            if any(cells):
                rows.append(cells)
        if rows:
            tables.append(tuple(rows))
    return tuple(tables)


def _normalize_section(
    raw: Any,
    warnings: list[str],
) -> DocumentSection | None:
    if not isinstance(raw, dict):
        warnings.append("Skipped a non-object section entry.")
        return None

    heading = normalize_text(raw.get("heading"))
    text = normalize_text(raw.get("text"))
    tables = _normalize_tables(raw.get("tables"))
    if not text and not tables:
        return None

    section_key = normalize_text(raw.get("section")).lower()
    if not section_key:
        section_key = map_heading_to_section(heading) if heading else "other"
    if not heading:
        heading = section_key.replace("_", " ").title()
        warnings.append(f"Section '{section_key}' had no heading; derived one.")

    return DocumentSection(
        section=section_key,
        heading=heading,
        text=text,
        tables=tables,
    )


def _normalize_sections(
    raw_sections: Any,
    warnings: list[str],
) -> tuple[DocumentSection, ...]:
    if not isinstance(raw_sections, list):
        raise DocumentLoadError("Document field 'sections' must be a list.")

    sections: list[DocumentSection] = []
    seen_headings: set[str] = set()
    for raw in raw_sections:
        section = _normalize_section(raw, warnings)
        if section is None:
            continue
        heading_key = section.heading.casefold()
        if heading_key in seen_headings:
            warnings.append(
                f"Dropped duplicate section heading '{section.heading}'."
            )
            continue
        seen_headings.add(heading_key)
        sections.append(section)
    return tuple(sections)


def _normalize_faqs(raw_faqs: Any, warnings: list[str]) -> tuple[FAQ, ...]:
    if raw_faqs is None:
        return ()
    if not isinstance(raw_faqs, list):
        warnings.append("Document field 'faqs' is not a list; ignored.")
        return ()

    faqs: list[FAQ] = []
    seen: set[tuple[str, str]] = set()
    for raw in raw_faqs:
        if not isinstance(raw, dict):
            continue
        question = normalize_text(raw.get("question"))
        answer = normalize_text(raw.get("answer"))
        key = (question.casefold(), answer.casefold())
        if question and answer and key not in seen:
            seen.add(key)
            faqs.append(FAQ(question=question, answer=answer))
    return tuple(faqs)


def _normalize_facts(raw_facts: Any) -> dict[str, Any]:
    if not isinstance(raw_facts, dict):
        return {}
    facts: dict[str, Any] = {}
    for key, value in raw_facts.items():
        if isinstance(value, str):
            facts[str(key)] = normalize_text(value)
        elif isinstance(value, list):
            facts[str(key)] = [
                normalize_text(item) if isinstance(item, str) else item
                for item in value
            ]
        else:
            facts[str(key)] = value
    return facts


def _is_iso_date(value: str) -> bool:
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def required_sections_for(document: Document) -> tuple[str, ...]:
    if document.page_type != "scheme":
        return ()
    required = list(REQUIRED_FACT_SECTIONS)
    identity = f"{document.doc_id} {document.scheme}".casefold()
    if "elss" in identity or "tax saver" in identity:
        required.extend(ELSS_REQUIRED_FACT_SECTIONS)
    return tuple(required)


def load_document(
    path: str | Path,
    *,
    allowed_urls: tuple[str, ...] | list[str] | set[str] | None = None,
    expected_url: str | None = None,
) -> Document:
    document_path = Path(path)
    if not document_path.exists():
        raise DocumentLoadError(
            f"Raw document not found: {document_path}. "
            "Run `python -m src.cli scrape` first."
        )

    try:
        raw = json.loads(document_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DocumentLoadError(
            f"Invalid JSON in {document_path}: {exc}"
        ) from exc
    except OSError as exc:
        raise DocumentLoadError(
            f"Could not read {document_path}: {exc}"
        ) from exc

    if not isinstance(raw, dict):
        raise DocumentLoadError(
            f"Raw document {document_path} must contain a JSON object."
        )

    missing_fields = [
        field_name
        for field_name in REQUIRED_DOCUMENT_FIELDS
        if field_name not in raw
        or (
            field_name != "sections"
            and not normalize_text(raw.get(field_name))
        )
    ]
    if missing_fields:
        raise DocumentLoadError(
            f"{document_path.name} is missing required field(s): "
            f"{', '.join(missing_fields)}."
        )

    url = normalize_text(raw["url"])
    allowlist = set(allowed_urls) if allowed_urls is not None else None
    if allowlist is not None and url not in allowlist:
        raise DocumentLoadError(
            f"{document_path.name} has URL outside the configured allowlist: "
            f"{url}"
        )
    if expected_url is not None and url != expected_url:
        raise DocumentLoadError(
            f"{document_path.name} URL {url} does not match configured URL "
            f"{expected_url}."
        )

    warnings: list[str] = []
    scraped_at = normalize_text(raw["scraped_at"])
    if not _is_iso_date(scraped_at):
        warnings.append(
            f"scraped_at '{scraped_at}' is not an ISO date (YYYY-MM-DD)."
        )

    sections = _normalize_sections(raw.get("sections"), warnings)
    if not sections:
        warnings.append("Document has no non-empty sections.")

    page_type = normalize_text(raw.get("page_type")) or page_type_from_url(url)
    faqs = _normalize_faqs(raw.get("faqs"), warnings)
    facts = _normalize_facts(raw.get("facts"))
    token_count = sum(count_tokens(section.text) for section in sections)

    return Document(
        doc_id=normalize_text(raw["doc_id"]),
        url=url,
        title=normalize_text(raw["title"]),
        scheme=normalize_text(raw["scheme"]),
        page_type=page_type,
        scraped_at=scraped_at,
        sections=sections,
        faqs=faqs,
        facts=facts,
        token_count=token_count,
        warnings=tuple(warnings),
    )


def load_manifest(manifest_path: str | Path | None = None) -> dict[str, Any]:
    path = Path(manifest_path) if manifest_path else DEFAULT_MANIFEST_PATH
    if not path.exists():
        raise DocumentLoadError(
            f"Manifest not found: {path}. "
            "Run `python -m src.cli scrape` first."
        )

    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DocumentLoadError(f"Invalid manifest JSON in {path}: {exc}") from exc
    except OSError as exc:
        raise DocumentLoadError(f"Could not read manifest {path}: {exc}") from exc

    if not isinstance(manifest, dict):
        raise DocumentLoadError(f"Manifest {path} must contain a JSON object.")

    sources = manifest.get("sources")
    if not isinstance(sources, list) or not sources:
        raise DocumentLoadError(
            f"Manifest {path} has no 'sources' list. "
            "Run `python -m src.cli scrape` first."
        )

    failures = [
        source
        for source in sources
        if not isinstance(source, dict) or source.get("status") != "ok"
    ]
    if failures:
        failing_urls = [
            str(source.get("url", "<unknown>"))
            for source in failures
        ]
        raise DocumentLoadError(
            "Manifest contains failed sources: "
            f"{', '.join(failing_urls)}. Fix scraping and rerun "
            "`python -m src.cli scrape` before loading."
        )

    return manifest


def _validate_manifest_sources(manifest: dict[str, Any], config: Config) -> None:
    sources = manifest.get("sources") or []
    manifest_urls = {
        normalize_text(source.get("url"))
        for source in sources
        if isinstance(source, dict)
    }
    expected_urls = set(config.data.source_urls)

    missing = expected_urls - manifest_urls
    extra = manifest_urls - expected_urls

    problems: list[str] = []
    if missing:
        problems.append(
            "is missing configured source URL(s): "
            f"{', '.join(sorted(missing))}"
        )
    if extra:
        problems.append(
            "contains URL(s) outside the configured allowlist: "
            f"{', '.join(sorted(extra))}"
        )
    if problems:
        raise DocumentLoadError(
            f"Manifest {'; '.join(problems)}. "
            "Rerun `python -m src.cli scrape`."
        )


def _write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temp_path, path)


def _document_report(
    document: Document,
    required: tuple[str, ...],
    missing: tuple[str, ...],
    warnings: list[str],
) -> dict[str, Any]:
    return {
        "doc_id": document.doc_id,
        "url": document.url,
        "title": document.title,
        "scheme": document.scheme,
        "page_type": document.page_type,
        "scraped_at": document.scraped_at,
        "status": "ok",
        "section_count": len(document.sections),
        "token_count": document.token_count,
        "sections": list(document.section_keys),
        "required_sections": list(required),
        "missing_sections": list(missing),
        "warnings": warnings,
        "error": None,
    }


def load_documents_with_stats(config: Config) -> LoadResult:
    report_path = config.paths.raw_dir / LOAD_REPORT_NAME
    expected_urls = tuple(config.data.source_urls)
    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "manifest_path": str(config.paths.manifest_path),
        "raw_dir": str(config.paths.raw_dir),
        "expected_document_count": len(expected_urls),
        "document_count": 0,
        "section_count": 0,
        "total_tokens": 0,
        "status": "error",
        "documents": [],
        "warnings": [],
    }

    try:
        manifest = load_manifest(config.paths.manifest_path)
        _validate_manifest_sources(manifest, config)
    except DocumentLoadError as exc:
        report["error"] = str(exc)
        _write_json_atomic(report_path, report)
        raise

    documents: list[Document] = []
    document_reports: list[dict[str, Any]] = []
    warnings: list[str] = []
    errors: list[str] = []

    for url in expected_urls:
        slug = slug_from_url(url)
        document_path = config.paths.raw_dir / f"{slug}.json"

        if not document_path.exists():
            message = (
                f"Raw document for {url} not found at {document_path}. "
                "Run `python -m src.cli scrape` first."
            )
            errors.append(message)
            warnings.append(message)
            document_reports.append(
                {
                    "doc_id": slug,
                    "url": url,
                    "status": "error",
                    "section_count": 0,
                    "token_count": 0,
                    "required_sections": [],
                    "missing_sections": [],
                    "warnings": [],
                    "error": message,
                }
            )
            continue

        try:
            document = load_document(
                document_path,
                allowed_urls=expected_urls,
                expected_url=url,
            )
        except DocumentLoadError as exc:
            errors.append(str(exc))
            warnings.append(str(exc))
            document_reports.append(
                {
                    "doc_id": slug,
                    "url": url,
                    "status": "error",
                    "section_count": 0,
                    "token_count": 0,
                    "required_sections": [],
                    "missing_sections": [],
                    "warnings": [],
                    "error": str(exc),
                }
            )
            continue

        required = required_sections_for(document)
        missing = tuple(
            section for section in required if section not in document.section_keys
        )
        document_warnings = list(document.warnings)
        if missing:
            message = (
                f"{document.doc_id}: missing required section(s): "
                f"{', '.join(missing)}."
            )
            document_warnings.append(message)
            warnings.append(message)

        documents.append(document)
        document_reports.append(
            _document_report(
                document,
                required,
                missing,
                document_warnings,
            )
        )

    total_sections = sum(len(document.sections) for document in documents)
    total_tokens = sum(document.token_count for document in documents)
    report.update(
        {
            "document_count": len(documents),
            "section_count": total_sections,
            "total_tokens": total_tokens,
            "documents": document_reports,
            "warnings": warnings,
            "status": (
                "ok"
                if not errors and len(documents) == len(expected_urls)
                else "error"
            ),
        }
    )
    _write_json_atomic(report_path, report)

    if errors:
        raise DocumentLoadError(
            "Document loading failed for "
            f"{len(errors)} source(s): {'; '.join(errors)}"
        )

    return LoadResult(
        documents=tuple(documents),
        stats=LoadStats(
            document_count=len(documents),
            section_count=total_sections,
            total_tokens=total_tokens,
        ),
        report=report,
        report_path=report_path,
        warnings=tuple(warnings),
    )


def load_documents(config: Config) -> list[Document]:
    return list(load_documents_with_stats(config).documents)
