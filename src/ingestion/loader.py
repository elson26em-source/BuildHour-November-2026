from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from html import unescape
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from src.config.schema import Config, ScrapingConfig

logger = logging.getLogger(__name__)

HEADING_TAGS = ("h1", "h2", "h3", "h4", "h5")
NOISE_TAGS = (
    "script",
    "style",
    "noscript",
    "svg",
    "header",
    "footer",
    "nav",
    "form",
    "iframe",
)
SKIP_AMC_HEADINGS = {
    "returns calculator",
    "view mutual funds from other amcs",
    "holdings",
    "understand terms",
}


class ScrapeError(RuntimeError):
    """Raised when a source page cannot be fetched or parsed."""

    def __init__(self, url: str, message: str) -> None:
        super().__init__(f"{url}: {message}")
        self.url = url
        self.message = message


@dataclass(frozen=True)
class ScrapeReport:
    results: tuple[dict[str, Any], ...]
    manifest_path: Path

    @property
    def success_count(self) -> int:
        return sum(1 for result in self.results if result["status"] == "ok")

    @property
    def failure_count(self) -> int:
        return len(self.results) - self.success_count


def slug_from_url(url: str) -> str:
    path = urlparse(url).path.strip("/")
    if path.startswith("mutual-funds/"):
        path = path[len("mutual-funds/") :]
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", path).strip("-").lower()
    return slug or "page"


def page_type_from_url(url: str) -> str:
    return "amc" if "/amc/" in urlparse(url).path else "scheme"


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = unescape(str(value))
    text = (
        text.replace("\u200b", "")
        .replace("\ufeff", "")
        .replace("\xa0", " ")
    )
    return re.sub(r"\s+", " ", text).strip()


def clean_multiline(value: Any) -> str:
    if value is None:
        return ""
    text = unescape(str(value))
    text = (
        text.replace("\u200b", "")
        .replace("\ufeff", "")
        .replace("\xa0", " ")
    )
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _fmt_number(value: Any, decimals: int = 2) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        formatted = f"{float(value):,.{decimals}f}"
        return formatted.rstrip("0").rstrip(".")
    return clean_text(value)


def _fmt_percent(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        text = f"{float(value):.{2}f}".rstrip("0").rstrip(".")
    else:
        text = clean_text(value)
    return text if text.endswith("%") else f"{text}%"


def _fmt_money_crore(value: Any) -> str | None:
    text = _fmt_number(value)
    return f"₹{text} Cr" if text else None


def _fmt_money(value: Any) -> str | None:
    text = _fmt_number(value)
    return f"₹{text}" if text else None


def _fmt_date(value: Any) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    date_part = text.replace("T", " ").split(" ")[0]
    for fmt in ("%Y-%m-%d", "%d-%b-%Y", "%d %b %Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(date_part, fmt).strftime("%d %b %Y")
        except ValueError:
            continue
    return date_part


def format_lock_in(value: Any) -> str:
    if not isinstance(value, dict):
        text = clean_text(value)
        return text or "No lock-in"
    parts: list[str] = []
    for key, label in (("years", "year"), ("months", "month"), ("days", "day")):
        raw = value.get(key)
        if raw in (None, "", 0, "0"):
            continue
        try:
            amount = int(raw)
        except (TypeError, ValueError):
            continue
        if amount:
            parts.append(f"{amount} {label}{'s' if amount != 1 else ''}")
    return ", ".join(parts) if parts else "No lock-in"


def format_risk(value: Any) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    text = re.sub(r"\s*riskometer\s*$", "", text, flags=re.IGNORECASE).strip()
    if text.lower().endswith("risk"):
        return text
    return f"{text} risk"


def extract_next_data(html: str) -> dict[str, Any] | None:
    match = re.search(
        r'<script id="__NEXT_DATA__"[^>]*>(?P<data>.*?)</script>',
        html,
        flags=re.DOTALL,
    )
    if not match:
        return None
    try:
        payload = json.loads(match.group("data"))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def html_fragment_to_text(fragment: Any) -> str:
    if not fragment:
        return ""
    soup = BeautifulSoup(str(fragment), "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    blocks: list[str] = []
    for element in soup.find_all(["h1", "h2", "h3", "h4", "p", "li"]):
        text = clean_text(element.get_text(" ", strip=True))
        if text and text not in blocks:
            blocks.append(text)
    if not blocks:
        blocks.append(clean_text(soup.get_text(" ", strip=True)))
    return "\n\n".join(block for block in blocks if block)


def extract_page_title(html: str, fallback: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    if soup.title:
        title = clean_text(soup.title.get_text(" ", strip=True))
        if title:
            return title
    return fallback


def extract_faqs(html: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    faqs: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def add_faq(question: Any, answer: Any) -> None:
        q = clean_text(question)
        a = html_fragment_to_text(answer)
        key = (q, a)
        if q and a and key not in seen:
            seen.add(key)
            faqs.append({"question": q, "answer": a})

    def consume(payload: Any) -> None:
        if isinstance(payload, list):
            for item in payload:
                consume(item)
            return
        if not isinstance(payload, dict):
            return
        graph = payload.get("@graph")
        if isinstance(graph, list):
            consume(graph)
        if payload.get("@type") == "FAQPage":
            for item in payload.get("mainEntity") or []:
                if not isinstance(item, dict):
                    continue
                answer = item.get("acceptedAnswer") or {}
                if isinstance(answer, list):
                    answer = answer[0] if answer else {}
                if isinstance(answer, dict):
                    add_faq(item.get("name"), answer.get("text"))

    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text()
        if not raw:
            continue
        try:
            consume(json.loads(raw))
        except (json.JSONDecodeError, TypeError):
            continue
    return faqs


def _make_section(
    key: str,
    heading: str,
    text: str,
    tables: list[list[list[str]]] | None = None,
) -> dict[str, Any] | None:
    body = clean_multiline(text)
    if not body and not tables:
        return None
    return {
        "section": key,
        "heading": heading,
        "text": body,
        "tables": tables or [],
    }


def map_heading_to_section(heading: str) -> str:
    lowered = heading.lower()
    if "expense" in lowered:
        return "expense_ratio"
    if "exit load" in lowered:
        return "exit_load"
    if "minimum sip" in lowered or "min. for sip" in lowered:
        return "minimum_sip"
    if "lock" in lowered:
        return "lock_in"
    if "risk" in lowered:
        return "riskometer"
    if "benchmark" in lowered:
        return "benchmark"
    if "statement" in lowered or "capital gain" in lowered or "download" in lowered:
        return "statement_download"
    if "key information" in lowered:
        return "amc_key_information"
    if "how to invest" in lowered:
        return "how_to_invest"
    if "list of" in lowered:
        return "amc_fund_list"
    if "closer look" in lowered:
        return "amc_details"
    if "hdfc mutual fund" in lowered:
        return "amc_overview"
    if "objective" in lowered:
        return "investment_objective"
    if "manager" in lowered:
        return "fund_managers"
    if "tax" in lowered:
        return "tax"
    return "other"


def extract_dom_sections(
    html: str,
    include_heading: Callable[[str], bool],
) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(NOISE_TAGS):
        tag.decompose()

    sections: list[dict[str, Any]] = []
    for heading_el in soup.find_all(HEADING_TAGS):
        heading = clean_text(heading_el.get_text(" ", strip=True))
        if not heading or not include_heading(heading):
            continue

        paragraphs: list[str] = []
        tables: list[list[list[str]]] = []
        rendered_tables: list[str] = []
        for element in heading_el.find_all_next():
            if element.name in HEADING_TAGS:
                break
            if element.name in ("p", "li"):
                text = clean_text(element.get_text(" ", strip=True))
                if text and text not in paragraphs:
                    paragraphs.append(text)
            elif element.name == "table":
                rows: list[list[str]] = []
                for row in element.find_all("tr"):
                    cells = [
                        clean_text(cell.get_text(" ", strip=True))
                        for cell in row.find_all(["th", "td"])
                    ]
                    if any(cells):
                        rows.append(cells)
                if rows and rows not in tables:
                    tables.append(rows)
                    rendered_tables.append(
                        "\n".join(" | ".join(cells) for cells in rows)
                    )

        body_parts = paragraphs + rendered_tables
        section = _make_section(
            map_heading_to_section(heading),
            heading,
            "\n\n".join(body_parts),
            tables,
        )
        if section:
            sections.append(section)
    return sections


def _pick(value: Any, default: Any = None) -> Any:
    return default if value in (None, "") else value


def _build_scheme_sections(
    data: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any], str]:
    scheme_name = clean_text(_pick(data.get("scheme_name"), data.get("fund_name")))
    fund_house = clean_text(data.get("fund_house"))
    category = clean_text(data.get("category"))
    sub_category = clean_text(data.get("sub_category"))
    plan_type = clean_text(data.get("plan_type"))
    scheme_type = clean_text(data.get("scheme_type"))

    expense_ratio = _fmt_percent(data.get("expense_ratio"))
    base_expense_ratio = _fmt_percent(data.get("base_expense_ratio"))
    expense_as_of = None
    history = data.get("historic_fund_expense")
    if isinstance(history, list) and history and isinstance(history[0], dict):
        expense_as_of = _fmt_date(history[0].get("as_on_date"))

    exit_load = clean_text(data.get("exit_load"))
    stamp_duty = clean_text(data.get("stamp_duty"))
    min_sip = _fmt_money(data.get("min_sip_investment"))
    min_lumpsum = _fmt_money(data.get("min_investment_amount"))
    lock_in_text = format_lock_in(data.get("lock_in"))

    risk_raw = None
    return_stats = data.get("return_stats")
    if isinstance(return_stats, list) and return_stats and isinstance(
        return_stats[0], dict
    ):
        risk_raw = return_stats[0].get("risk")
    risk_raw = risk_raw or data.get("nfo_risk")
    riskometer = format_risk(risk_raw)

    benchmark_name = clean_text(data.get("benchmark_name"))
    benchmark_short = clean_text(data.get("benchmark"))
    aum = _fmt_money_crore(data.get("aum"))
    nav = _fmt_money(data.get("nav"))
    nav_date = _fmt_date(data.get("nav_date"))
    launch_date = _fmt_date(data.get("launch_date"))

    managers: list[str] = []
    manager_details = data.get("fund_manager_details")
    if isinstance(manager_details, list):
        for manager in manager_details:
            if not isinstance(manager, dict):
                continue
            name = clean_text(manager.get("person_name"))
            if name and name not in managers:
                managers.append(name)

    description = clean_text(data.get("description"))
    category_info = data.get("category_info")
    tax_impact = ""
    if isinstance(category_info, dict):
        tax_impact = clean_text(category_info.get("tax_impact"))

    facts = {
        "scheme_name": scheme_name,
        "fund_house": fund_house,
        "category": category,
        "sub_category": sub_category,
        "plan_type": plan_type,
        "scheme_type": scheme_type,
        "expense_ratio": expense_ratio,
        "base_expense_ratio": base_expense_ratio,
        "expense_as_of": expense_as_of,
        "exit_load": exit_load,
        "stamp_duty": stamp_duty,
        "minimum_sip_investment": min_sip,
        "minimum_lumpsum_investment": min_lumpsum,
        "lock_in": lock_in_text,
        "riskometer": riskometer,
        "benchmark_name": benchmark_name,
        "benchmark_short": benchmark_short,
        "aum_crore": aum,
        "nav": nav,
        "nav_date": nav_date,
        "launch_date": launch_date,
        "fund_managers": managers,
        "investment_objective": description,
        "tax_impact": tax_impact,
    }

    sections: list[dict[str, Any]] = []

    article = "an" if category[:1].lower() in "aeiou" else "a"
    overview_parts = [
        f"{scheme_name} is {article} {category} {sub_category} scheme from {fund_house}."
        if scheme_name
        else ""
    ]
    if plan_type:
        overview_parts.append(f"Plan type: {plan_type}.")
    if launch_date:
        overview_parts.append(f"Launched on {launch_date}.")
    if aum:
        overview_parts.append(f"Fund size (AUM): {aum}.")
    if nav:
        as_of = f" as of {nav_date}" if nav_date else ""
        overview_parts.append(f"NAV: {nav}{as_of}.")
    section = _make_section(
        "scheme_overview",
        "Scheme Overview",
        " ".join(part for part in overview_parts if part),
    )
    if section:
        sections.append(section)

    if expense_ratio:
        parts = [f"Expense ratio: {expense_ratio}."]
        if base_expense_ratio:
            parts.append(f"Base expense ratio: {base_expense_ratio}.")
        if expense_as_of:
            parts.append(f"As of {expense_as_of}.")
        section = _make_section("expense_ratio", "Expense Ratio", " ".join(parts))
        if section:
            sections.append(section)

    if exit_load:
        text = exit_load
        if stamp_duty:
            separator = "" if text.endswith((".", "!", "?")) else "."
            text = f"{text}{separator} Stamp duty: {stamp_duty}"
        section = _make_section("exit_load", "Exit Load", text)
        if section:
            sections.append(section)

    if min_sip:
        section = _make_section(
            "minimum_sip", "Minimum SIP", f"Minimum SIP investment: {min_sip}."
        )
        if section:
            sections.append(section)

    if min_lumpsum:
        section = _make_section(
            "minimum_investment",
            "Minimum Investment",
            f"Minimum lumpsum investment: {min_lumpsum}.",
        )
        if section:
            sections.append(section)

    lock_in_sentence = (
        "No lock-in period."
        if lock_in_text == "No lock-in"
        else f"Lock-in period: {lock_in_text}."
    )
    section = _make_section("lock_in", "Lock-in", lock_in_sentence)
    if section:
        sections.append(section)

    if riskometer:
        section = _make_section(
            "riskometer", "Riskometer", f"Riskometer: {riskometer}."
        )
        if section:
            sections.append(section)

    if benchmark_name or benchmark_short:
        benchmark_text = benchmark_name or benchmark_short
        if benchmark_name and benchmark_short and benchmark_short != benchmark_name:
            benchmark_text = f"{benchmark_name} ({benchmark_short})"
        section = _make_section(
            "benchmark", "Benchmark", f"Fund benchmark: {benchmark_text}."
        )
        if section:
            sections.append(section)

    if managers:
        section = _make_section(
            "fund_managers",
            "Fund Managers",
            f"Fund managers: {', '.join(managers)}.",
        )
        if section:
            sections.append(section)

    if description:
        section = _make_section(
            "investment_objective", "Investment Objective", description
        )
        if section:
            sections.append(section)

    if tax_impact:
        section = _make_section("tax", "Tax", tax_impact)
        if section:
            sections.append(section)

    return sections, facts, scheme_name or "HDFC Mutual Fund"


def _amc_part(data: Any, index: int) -> dict[str, Any]:
    if isinstance(data, list):
        return data[index] if index < len(data) and isinstance(data[index], dict) else {}
    if isinstance(data, dict):
        for key in (index, str(index)):
            value = data.get(key)
            if isinstance(value, dict):
                return value
    return {}


def _build_amc_sections(
    data: Any,
) -> tuple[list[dict[str, Any]], dict[str, Any], str]:
    parts = _amc_part(data, 1)
    funds_part = _amc_part(data, 2)
    amcs_part = _amc_part(data, 0)

    content_list = parts.get("contentList")
    sections: list[dict[str, Any]] = []
    if isinstance(content_list, list):
        for item in content_list:
            if not isinstance(item, dict):
                continue
            heading = clean_text(item.get("title"))
            if not heading or heading.lower() in SKIP_AMC_HEADINGS:
                continue
            text = html_fragment_to_text(item.get("content"))
            section = _make_section(
                map_heading_to_section(heading), heading, text
            )
            if section:
                sections.append(section)

    fund_count = None
    total = funds_part.get("total_results")
    if isinstance(total, (int, float)):
        fund_count = int(total)

    rank = None
    amcs = amcs_part.get("amcs")
    if isinstance(amcs, list):
        for amc in amcs:
            if not isinstance(amc, dict):
                continue
            if clean_text(amc.get("search_id")) == "hdfc-mutual-funds":
                rank = amc.get("rank")
                break

    facts = {
        "amc_name": "HDFC Mutual Fund",
        "fund_count": fund_count,
        "rank": rank,
    }
    return sections, facts, "HDFC Mutual Fund"


def build_document(
    url: str,
    html: str,
    *,
    scraped_at: str,
    fetch_method: str,
    http_status: int,
) -> dict[str, Any]:
    slug = slug_from_url(url)
    page_type = page_type_from_url(url)
    next_data = extract_next_data(html)
    if not next_data:
        raise ScrapeError(url, "embedded __NEXT_DATA__ payload was not found")

    page_props = next_data.get("props", {}).get("pageProps", {})
    if not isinstance(page_props, dict):
        raise ScrapeError(url, "pageProps payload is not an object")

    faqs = extract_faqs(html)
    dom_statement_sections = extract_dom_sections(
        html,
        lambda heading: any(
            keyword in heading.lower()
            for keyword in ("statement", "capital gain", "download")
        ),
    )

    if page_type == "scheme":
        scheme_data = page_props.get("mfServerSideData")
        if not isinstance(scheme_data, dict):
            raise ScrapeError(url, "mfServerSideData payload was not found")
        sections, facts, scheme = _build_scheme_sections(scheme_data)
        structured_source = "mfServerSideData"
        default_title = clean_text(scheme_data.get("meta_title")) or scheme
    else:
        amc_data = page_props.get("amcMainPageData")
        if amc_data is None:
            raise ScrapeError(url, "amcMainPageData payload was not found")
        sections, facts, scheme = _build_amc_sections(amc_data)
        structured_source = "amcMainPageData"
        default_title = scheme

        dom_headings = {
            "key information about hdfc mutual fund",
            "list of hdfc mutual fund in india",
            "let's have a closer look",
            "lets have a closer look",
        }
        existing = {section["heading"].lower() for section in sections}
        for section in extract_dom_sections(
            html, lambda heading: heading.lower() in dom_headings
        ):
            if section["heading"].lower() not in existing:
                sections.append(section)
                existing.add(section["heading"].lower())

    existing = {section["heading"].lower() for section in sections}
    for section in dom_statement_sections:
        if section["heading"].lower() not in existing:
            sections.append(section)
            existing.add(section["heading"].lower())

    title = default_title or extract_page_title(html, scheme)
    return {
        "doc_id": slug,
        "url": url,
        "title": title,
        "scheme": scheme,
        "page_type": page_type,
        "scraped_at": scraped_at,
        "sections": sections,
        "faqs": faqs,
        "facts": facts,
        "raw_html_path": f"artifacts/01_raw/html/{slug}.html",
        "extraction": {
            "structured_source": structured_source,
            "next_data_found": True,
            "section_count": len(sections),
            "faq_count": len(faqs),
            "fetch_method": fetch_method,
            "http_status": http_status,
        },
    }


def _fetch_with_playwright(url: str, scraping: ScrapingConfig) -> str:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - depends on optional install
        raise ScrapeError(
            url,
            "static fetch failed and Playwright fallback is not installed",
        ) from exc

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(user_agent=scraping.user_agent)
            page.goto(
                url,
                wait_until="networkidle",
                timeout=scraping.timeout_seconds * 1000,
            )
            html = page.content()
            browser.close()
    except Exception as exc:  # pragma: no cover - network/browser dependent
        raise ScrapeError(url, f"Playwright fetch failed: {exc}") from exc

    if len(html) < 2_000:
        raise ScrapeError(url, "Playwright returned an unexpectedly small page")
    return html


def fetch_html(
    url: str,
    scraping: ScrapingConfig,
    session: requests.Session | None = None,
) -> tuple[str, str, int]:
    session = session or requests.Session()
    headers = {
        "User-Agent": scraping.user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-IN,en;q=0.9",
    }

    last_error: Exception | None = None
    attempts = max(1, scraping.max_retries + 1)
    for attempt in range(attempts):
        try:
            response = session.get(
                url,
                headers=headers,
                timeout=scraping.timeout_seconds,
            )
            if response.status_code != 200:
                raise ScrapeError(
                    url, f"unexpected HTTP status {response.status_code}"
                )
            html = response.content.decode("utf-8", errors="replace")
            if len(html) < 2_000:
                raise ScrapeError(url, "response was unexpectedly small")
            return html, "requests", response.status_code
        except (requests.RequestException, ScrapeError) as exc:
            last_error = exc
            if attempt < attempts - 1:
                wait = 2**attempt
                logger.warning(
                    "Fetch failed for %s (attempt %d/%d): %s; retrying in %ss",
                    url,
                    attempt + 1,
                    attempts,
                    exc,
                    wait,
                )
                time.sleep(wait)

    if scraping.use_playwright_fallback:
        html = _fetch_with_playwright(url, scraping)
        return html, "playwright", 200

    raise ScrapeError(url, f"fetch failed after {attempts} attempts: {last_error}")


def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(text, encoding="utf-8")
    os.replace(temp_path, path)


def _write_json_atomic(path: Path, payload: Any) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    _write_text_atomic(path, text + "\n")


def scrape_sources(config: Config) -> ScrapeReport:
    config.paths.raw_dir.mkdir(parents=True, exist_ok=True)
    config.paths.html_dir.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    results: list[dict[str, Any]] = []
    total = len(config.data.source_urls)

    for index, url in enumerate(config.data.source_urls, start=1):
        slug = slug_from_url(url)
        started = time.perf_counter()
        scraped_at = date.today().isoformat()
        logger.info("[%d/%d] Fetching %s", index, total, url)
        try:
            html, fetch_method, http_status = fetch_html(
                url, config.scraping, session=session
            )
            html_path = config.paths.html_dir / f"{slug}.html"
            _write_text_atomic(html_path, html)

            document = build_document(
                url,
                html,
                scraped_at=scraped_at,
                fetch_method=fetch_method,
                http_status=http_status,
            )
            try:
                document["raw_html_path"] = html_path.relative_to(
                    config.paths.artifacts_dir.parent
                ).as_posix()
            except ValueError:
                document["raw_html_path"] = str(html_path)
            json_path = config.paths.raw_dir / f"{slug}.json"
            _write_json_atomic(json_path, document)

            duration_ms = int((time.perf_counter() - started) * 1000)
            result = {
                "url": url,
                "doc_id": slug,
                "page_type": document["page_type"],
                "scheme": document["scheme"],
                "status": "ok",
                "scraped_at": scraped_at,
                "http_status": http_status,
                "fetch_method": fetch_method,
                "bytes": len(html.encode("utf-8")),
                "section_count": len(document["sections"]),
                "faq_count": len(document["faqs"]),
                "json_path": str(json_path),
                "html_path": str(html_path),
                "duration_ms": duration_ms,
            }
            logger.info(
                "  saved %s (%d sections, %d FAQs, %s)",
                slug,
                result["section_count"],
                result["faq_count"],
                fetch_method,
            )
        except Exception as exc:  # noqa: BLE001 - recorded per source
            duration_ms = int((time.perf_counter() - started) * 1000)
            logger.error("  failed %s: %s", slug, exc)
            result = {
                "url": url,
                "doc_id": slug,
                "page_type": page_type_from_url(url),
                "scheme": "",
                "status": "error",
                "scraped_at": scraped_at,
                "http_status": None,
                "fetch_method": None,
                "bytes": 0,
                "section_count": 0,
                "faq_count": 0,
                "json_path": None,
                "html_path": None,
                "duration_ms": duration_ms,
                "error": str(exc),
            }
        results.append(result)

        if index < total and config.scraping.delay_seconds > 0:
            time.sleep(config.scraping.delay_seconds)

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_count": total,
        "success_count": sum(1 for r in results if r["status"] == "ok"),
        "failure_count": sum(1 for r in results if r["status"] != "ok"),
        "sources": results,
    }
    _write_json_atomic(config.paths.manifest_path, manifest)
    return ScrapeReport(results=tuple(results), manifest_path=config.paths.manifest_path)
