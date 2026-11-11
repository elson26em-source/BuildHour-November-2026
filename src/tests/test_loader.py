from __future__ import annotations

import json

from src.ingestion.loader import (
    build_document,
    clean_text,
    format_lock_in,
    format_risk,
    slug_from_url,
)


def _html_with_next_data(page_props: dict, body: str = "") -> str:
    payload = {"props": {"pageProps": page_props}}
    return (
        "<html><head>"
        '<script id="__NEXT_DATA__" type="application/json">'
        f"{json.dumps(payload)}"
        "</script></head><body>"
        f"{body}"
        "</body></html>"
    )


def test_slug_from_url() -> None:
    assert (
        slug_from_url(
            "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth"
        )
        == "hdfc-large-cap-fund-direct-growth"
    )
    assert (
        slug_from_url("https://groww.in/mutual-funds/amc/hdfc-mutual-funds")
        == "amc-hdfc-mutual-funds"
    )


def test_clean_text() -> None:
    assert clean_text("  A\u00a0 B \u200bC\n") == "A B C"


def test_format_lock_in() -> None:
    assert format_lock_in({"years": 3, "months": 0, "days": 0}) == "3 years"
    assert format_lock_in({"years": None, "months": None, "days": None}) == (
        "No lock-in"
    )
    assert format_lock_in({"years": 0, "months": 1, "days": 15}) == "1 month, 15 days"


def test_format_risk() -> None:
    assert format_risk("Very High") == "Very High risk"
    assert format_risk("Moderately High Riskometer") == "Moderately High risk"
    assert format_risk("") is None


def test_build_scheme_document() -> None:
    scheme_data = {
        "scheme_name": "HDFC Large Cap Fund Direct Growth",
        "fund_house": "HDFC Mutual Fund",
        "category": "Equity",
        "sub_category": "Large Cap",
        "plan_type": "Direct",
        "scheme_type": "Growth",
        "expense_ratio": "1.01",
        "base_expense_ratio": "0.83",
        "historic_fund_expense": [
            {"expense_ratio": 1.01, "as_on_date": "2026-11-04T00:00:00"}
        ],
        "exit_load": "Exit load of 1% if redeemed within 1 year",
        "stamp_duty": "0.005% (from July 1st, 2020)",
        "min_sip_investment": 100,
        "min_investment_amount": 100,
        "lock_in": {"years": None, "months": None, "days": None},
        "return_stats": [{"risk": "Very High"}],
        "benchmark_name": "NIFTY 100 Total Return Index",
        "benchmark": "NIFTY 100 TRI",
        "aum": 37293.95,
        "nav": 1257.172,
        "nav_date": "06-Nov-2026",
        "launch_date": "01-Jan-2013",
        "fund_manager_details": [{"person_name": "Rahul Baijal"}],
        "description": "The scheme seeks to provide long-term capital appreciation.",
        "category_info": {"tax_impact": "Taxed as equity."},
    }
    html = _html_with_next_data(
        {"mfServerSideData": scheme_data},
        body="<h2>Statement</h2><p>Download your account statement from the AMC.</p>",
    )

    document = build_document(
        "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
        html,
        scraped_at="2026-11-09",
        fetch_method="requests",
        http_status=200,
    )

    keys = {section["section"] for section in document["sections"]}
    assert document["page_type"] == "scheme"
    assert document["scheme"] == "HDFC Large Cap Fund Direct Growth"
    assert document["facts"]["expense_ratio"] == "1.01%"
    assert document["facts"]["riskometer"] == "Very High risk"
    assert document["facts"]["lock_in"] == "No lock-in"
    assert {
        "scheme_overview",
        "expense_ratio",
        "exit_load",
        "minimum_sip",
        "minimum_investment",
        "lock_in",
        "riskometer",
        "benchmark",
        "fund_managers",
        "investment_objective",
        "tax",
        "statement_download",
    } <= keys
    assert "Expense ratio: 1.01%." in document["sections"][1]["text"]


def test_build_elss_document_lock_in() -> None:
    scheme_data = {
        "scheme_name": "HDFC ELSS Tax Saver Fund Direct Plan Growth",
        "fund_house": "HDFC Mutual Fund",
        "category": "Equity",
        "sub_category": "ELSS",
        "expense_ratio": "1.2",
        "lock_in": {"years": 3, "months": 0, "days": 0},
        "return_stats": [{"risk": "Very High"}],
        "min_sip_investment": 500,
    }
    html = _html_with_next_data({"mfServerSideData": scheme_data})
    document = build_document(
        "https://groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth",
        html,
        scraped_at="2026-11-09",
        fetch_method="requests",
        http_status=200,
    )

    lock_section = next(
        section
        for section in document["sections"]
        if section["section"] == "lock_in"
    )
    assert lock_section["text"] == "Lock-in period: 3 years."


def test_build_amc_document() -> None:
    amc_data = {
        "0": {
            "amcs": [
                {"search_id": "hdfc-mutual-funds", "name": "HDFC Mutual Fund", "rank": "2"}
            ]
        },
        "1": {
            "contentList": [
                {
                    "title": "HDFC Mutual Fund",
                    "content": "<p>HDFC Mutual Fund is an asset management company.</p>",
                },
                {
                    "title": "How to invest in HDFC Mutual Funds?",
                    "content": "<p>Invest online or offline.</p>",
                },
                {
                    "title": "Returns calculator",
                    "content": "<p>Ignore returns.</p>",
                },
            ]
        },
        "2": {"total_results": 84, "content": []},
    }
    html = _html_with_next_data(
        {"amcMainPageData": amc_data},
        body="<h2>Key information about HDFC Mutual Fund</h2><p>Key facts.</p>",
    )
    document = build_document(
        "https://groww.in/mutual-funds/amc/hdfc-mutual-funds",
        html,
        scraped_at="2026-11-09",
        fetch_method="requests",
        http_status=200,
    )

    keys = {section["section"] for section in document["sections"]}
    assert document["page_type"] == "amc"
    assert document["scheme"] == "HDFC Mutual Fund"
    assert document["facts"]["fund_count"] == 84
    assert {"amc_overview", "how_to_invest", "amc_key_information"} <= keys
    assert "other" not in {
        section["section"]
        for section in document["sections"]
        if section["heading"] == "Returns calculator"
    }
