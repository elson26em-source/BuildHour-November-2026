from __future__ import annotations

from typing import Sequence

from src.retrieval.retriever import RetrievalHit

SYSTEM_PROMPT = """You are a facts-only mutual fund FAQ assistant for HDFC mutual fund pages.

Rules:
- Use only the supplied context. Do not use outside knowledge.
- Answer in 1-2 short sentences, never more than 3 sentences.
- Do not give investment advice, recommendations, rankings, comparisons, or return/performance predictions.
- Do not invent facts, dates, or URLs.
- Do not include URLs in your answer. The system will add exactly one citation.
- If the context does not contain the answer, reply exactly: Not available from sources.
"""

STRICT_SYSTEM_PROMPT = SYSTEM_PROMPT + """
Your previous answer failed validation. Return only a concise factual answer
using the context. Do not add explanations, caveats, or extra links.
"""


def build_system_prompt(*, strict: bool = False) -> str:
    return STRICT_SYSTEM_PROMPT if strict else SYSTEM_PROMPT


def build_context(hits: Sequence[RetrievalHit]) -> str:
    blocks: list[str] = []
    for index, hit in enumerate(hits, start=1):
        blocks.append(
            "\n".join(
                (
                    f"[{index}] Scheme: {hit.scheme}",
                    f"Section: {hit.section}",
                    f"Heading: {hit.heading}",
                    f"Source: {hit.source_url}",
                    f"Last updated: {hit.scraped_at}",
                    f"Text: {hit.text}",
                )
            )
        )
    return "\n\n".join(blocks)


def build_user_prompt(query: str, hits: Sequence[RetrievalHit]) -> str:
    return (
        f"Question: {query}\n\n"
        "Context:\n"
        f"{build_context(hits)}\n\n"
        "Answer using only the context above."
    )


def build_messages(
    query: str,
    hits: Sequence[RetrievalHit],
    *,
    strict: bool = False,
) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": build_system_prompt(strict=strict)},
        {"role": "user", "content": build_user_prompt(query, hits)},
    ]
