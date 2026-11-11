from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from src.config.loader import PROJECT_ROOT, load_config
from src.ingestion.document_loader import (
    DocumentLoadError,
    load_document,
    load_documents,
    load_documents_with_stats,
    load_manifest,
    normalize_text,
)
from src.ingestion.loader import slug_from_url


def _base_sections() -> list[dict]:
    return [
        {
            "section": "expense_ratio",
            "heading": "Expense Ratio",
            "text": "Expense ratio: 1.01%.",
            "tables": [],
        },
        {
            "section": "exit_load",
            "heading": "Exit Load",
            "text": "Exit load of 1% within 1 year.",
            "tables": [],
        },
        {
            "section": "minimum_sip",
            "heading": "Minimum SIP",
            "text": "Minimum SIP investment: Rs 100.",
            "tables": [],
        },
        {
            "section": "lock_in",
            "heading": "Lock-in",
            "text": "Lock-in period: 3 years.",
            "tables": [],
        },
        {
            "section": "riskometer",
            "heading": "Riskometer",
            "text": "Riskometer: Very High risk.",
            "tables": [],
        },
        {
            "section": "benchmark",
            "heading": "Benchmark",
            "text": "Fund benchmark: NIFTY 100 TRI.",
            "tables": [],
        },
    ]


def _write_document(
    raw_dir: Path,
    url: str,
    *,
    doc_id: str | None = None,
    page_type: str | None = None,
    scheme: str = "HDFC Test Fund",
    sections: list[dict] | None = None,
    faqs: list[dict] | None = None,
) -> Path:
    slug = doc_id or slug_from_url(url)
    document = {
        "doc_id": slug,
        "url": url,
        "title": f"{scheme} - Groww",
        "scheme": scheme,
        "page_type": page_type
        or ("amc" if "/amc/" in url else "scheme"),
        "scraped_at": "2026-11-09",
        "sections": sections if sections is not None else _base_sections(),
        "faqs": faqs or [],
        "facts": {},
    }
    path = raw_dir / f"{slug}.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _make_manifest(raw_dir: Path, urls: tuple[str, ...], status: str = "ok") -> Path:
    manifest = {
        "generated_at": "2026-11-09T00:00:00+00:00",
        "source_count": len(urls),
        "success_count": len(urls) if status == "ok" else 0,
        "failure_count": 0 if status == "ok" else len(urls),
        "sources": [
            {"url": url, "doc_id": slug_from_url(url), "status": status}
            for url in urls
        ],
    }
    path = raw_dir / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def _config_with_paths(tmp_path: Path):
    config = load_config(require_api_key=False)
    raw_dir = tmp_path / "01_raw"
    raw_dir.mkdir()
    paths = replace(
        config.paths,
        raw_dir=raw_dir,
        manifest_path=raw_dir / "manifest.json",
    )
    return replace(config, paths=paths), raw_dir


def _write_all_sources(raw_dir: Path, urls: tuple[str, ...]) -> None:
    for url in urls:
        _write_document(raw_dir, url, scheme="HDFC Mutual Fund")


def test_normalize_text_strips_whitespace_and_zero_width() -> None:
    assert normalize_text("  A\u00a0 B\u200b\n C  ") == "A B C"


def test_load_document_normalizes_dedupes_and_drops_empty(tmp_path: Path) -> None:
    url = "https://groww.in/mutual-funds/hdfc-test-fund-direct-growth"
    path = _write_document(
        tmp_path,
        url,
        sections=[
            {
                "section": "expense_ratio",
                "heading": "Expense Ratio",
                "text": "  Expense\u00a0ratio:\u200b  1.01% \n",
                "tables": [],
            },
            {
                "section": "expense_ratio",
                "heading": "Expense Ratio",
                "text": "Duplicate.",
                "tables": [],
            },
            {
                "section": "other",
                "heading": "Empty",
                "text": "   ",
                "tables": [],
            },
            {
                "section": "exit_load",
                "heading": "Exit Load",
                "text": "",
                "tables": [[["Within 1 year", "1%"]]],
            },
        ],
    )

    document = load_document(path, allowed_urls=(url,))

    assert document.sections[0].text == "Expense ratio: 1.01%"
    assert document.sections[1].section == "exit_load"
    assert document.sections[1].tables == ((("Within 1 year", "1%"),),)
    assert len(document.sections) == 2
    assert any("duplicate" in warning.lower() for warning in document.warnings)


def test_load_document_rejects_url_outside_allowlist(tmp_path: Path) -> None:
    url = "https://groww.in/mutual-funds/hdfc-test-fund-direct-growth"
    path = _write_document(tmp_path, url)

    with pytest.raises(DocumentLoadError, match="allowlist"):
        load_document(
            path,
            allowed_urls=(
                "https://groww.in/mutual-funds/hdfc-other-fund-direct-growth",
            ),
        )


def test_load_documents_returns_five_and_writes_report(tmp_path: Path) -> None:
    config, raw_dir = _config_with_paths(tmp_path)
    _write_all_sources(raw_dir, config.data.source_urls)
    _make_manifest(raw_dir, config.data.source_urls)

    result = load_documents_with_stats(config)

    assert len(result.documents) == 5
    assert result.stats.document_count == 5
    assert result.stats.section_count == 30
    assert result.stats.total_tokens > 0
    assert result.report["status"] == "ok"
    assert result.report_path.exists()

    elss = next(
        document
        for document in result.report["documents"]
        if "elss" in document["doc_id"]
    )
    assert "lock_in" in elss["required_sections"]
    assert elss["missing_sections"] == []


def test_load_documents_returns_list(tmp_path: Path) -> None:
    config, raw_dir = _config_with_paths(tmp_path)
    _write_all_sources(raw_dir, config.data.source_urls)
    _make_manifest(raw_dir, config.data.source_urls)

    documents = load_documents(config)

    assert isinstance(documents, list)
    assert len(documents) == 5
    assert all(document.url in config.data.source_urls for document in documents)


def test_missing_required_section_is_reported(tmp_path: Path) -> None:
    config, raw_dir = _config_with_paths(tmp_path)
    sections = [
        section
        for section in _base_sections()
        if section["section"] != "benchmark"
    ]
    for url in config.data.source_urls:
        _write_document(raw_dir, url, sections=sections)
    _make_manifest(raw_dir, config.data.source_urls)

    result = load_documents_with_stats(config)

    assert result.report["status"] == "ok"
    assert any("benchmark" in warning for warning in result.warnings)
    scheme_report = next(
        document
        for document in result.report["documents"]
        if document["page_type"] == "scheme"
    )
    assert scheme_report["missing_sections"] == ["benchmark"]


def test_missing_manifest_raises_and_writes_report(tmp_path: Path) -> None:
    config, _ = _config_with_paths(tmp_path)

    with pytest.raises(DocumentLoadError, match="scrape"):
        load_documents_with_stats(config)

    report_path = config.paths.raw_dir / "load_report.json"
    assert report_path.exists()
    assert json.loads(report_path.read_text(encoding="utf-8"))["status"] == "error"


def test_failed_manifest_raises(tmp_path: Path) -> None:
    config, raw_dir = _config_with_paths(tmp_path)
    _write_all_sources(raw_dir, config.data.source_urls)
    _make_manifest(raw_dir, config.data.source_urls, status="error")

    with pytest.raises(DocumentLoadError, match="failed sources"):
        load_documents_with_stats(config)


def test_missing_raw_file_raises(tmp_path: Path) -> None:
    config, raw_dir = _config_with_paths(tmp_path)
    for url in config.data.source_urls[:-1]:
        _write_document(raw_dir, url)
    _make_manifest(raw_dir, config.data.source_urls)

    with pytest.raises(DocumentLoadError, match="not found"):
        load_documents_with_stats(config)


def test_manifest_url_outside_allowlist_raises(tmp_path: Path) -> None:
    config, raw_dir = _config_with_paths(tmp_path)
    _write_all_sources(raw_dir, config.data.source_urls)
    manifest = json.loads(
        _make_manifest(raw_dir, config.data.source_urls).read_text(
            encoding="utf-8"
        )
    )
    manifest["sources"][0]["url"] = "https://groww.in/mutual-funds/other"
    (raw_dir / "manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )

    with pytest.raises(DocumentLoadError, match="outside the configured allowlist"):
        load_documents_with_stats(config)


def test_load_manifest_defaults_to_project_manifest() -> None:
    if not (PROJECT_ROOT / "artifacts/01_raw/manifest.json").exists():
        pytest.skip("Project manifest has not been generated yet.")
    manifest = load_manifest()
    assert manifest["success_count"] == 5
    assert manifest["failure_count"] == 0
