from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from src.config.loader import ConfigError, load_config
from src.evaluation.evaluator import (
    EvaluationError,
    MockLLM,
    api_key_available,
    evaluate_cases,
    load_eval_cases,
    write_report,
)
from src.generation.answerer import AnswerError, AnswerResult, Answerer
from src.ingestion.chunker import ChunkingError, run_chunking
from src.ingestion.document_loader import (
    DocumentLoadError,
    load_documents_with_stats,
)
from src.ingestion.embedder import EmbeddingError, embed_chunks
from src.ingestion.indexer import IndexingError, index_chunks
from src.ingestion.loader import ScrapeReport, scrape_sources
from src.retrieval.retriever import RetrievalError, Retriever

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )


def _print_report(report: ScrapeReport) -> None:
    for result in report.results:
        if result["status"] == "ok":
            print(
                f"  OK   {result['doc_id']}  "
                f"sections={result['section_count']}  "
                f"faqs={result['faq_count']}  "
                f"method={result['fetch_method']}"
            )
        else:
            print(f"  FAIL {result['doc_id']}  {result.get('error', '')}")

    print(
        f"\nScrape complete: {report.success_count} succeeded, "
        f"{report.failure_count} failed."
    )
    print(f"Manifest: {report.manifest_path}")


def _run_scrape(config_path: str | None) -> int:
    try:
        config = load_config(config_path, require_api_key=False)
    except ConfigError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 2

    report = scrape_sources(config)
    _print_report(report)
    return 0 if report.failure_count == 0 else 1


def _run_load(config_path: str | None) -> int:
    try:
        config = load_config(config_path, require_api_key=False)
    except ConfigError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 2

    try:
        result = load_documents_with_stats(config)
    except DocumentLoadError as exc:
        print(f"Load error: {exc}", file=sys.stderr)
        return 1

    for document in result.report["documents"]:
        if document["status"] == "ok":
            print(
                f"  OK   {document['doc_id']}  "
                f"sections={document['section_count']}  "
                f"tokens={document['token_count']}"
            )
        else:
            print(f"  FAIL {document['doc_id']}  {document.get('error', '')}")

    for warning in result.warnings:
        print(f"  WARN {warning}")

    print(
        f"\nLoaded {result.stats.document_count} documents, "
        f"{result.stats.section_count} sections, "
        f"{result.stats.total_tokens} tokens."
    )
    print(f"Report: {result.report_path}")
    return 0


def _run_chunk(config_path: str | None) -> int:
    try:
        config = load_config(config_path, require_api_key=False)
    except ConfigError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 2

    try:
        result = run_chunking(config)
    except (DocumentLoadError, ChunkingError) as exc:
        print(f"Chunk error: {exc}", file=sys.stderr)
        return 1

    for warning in result.warnings:
        print(f"  WARN {warning}")

    print(
        f"\nChunked {result.stats.document_count} documents "
        f"({result.stats.section_count} sections) into "
        f"{result.stats.chunk_count} chunks "
        f"({result.stats.total_tokens} tokens)."
    )
    print(
        f"Token range: {result.stats.min_chunk_tokens}-"
        f"{result.stats.max_chunk_tokens} "
        f"(limit {config.chunking.max_tokens})."
    )
    print(f"Chunks: {result.chunks_path}")
    print(f"Strategy: {result.strategy_path}")
    return 0


def _run_embed(config_path: str | None) -> int:
    try:
        config = load_config(config_path, require_api_key=False)
    except ConfigError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 2

    try:
        result = embed_chunks(config)
    except (ChunkingError, EmbeddingError) as exc:
        print(f"Embedding error: {exc}", file=sys.stderr)
        return 1

    for warning in result.warnings:
        print(f"  WARN {warning}")

    print(
        f"\nEmbedded {result.chunk_count} chunks with "
        f"{result.model_name} into {result.dimension}-dimensional vectors."
    )
    print(f"Embeddings: {result.embeddings_path}")
    print(f"Manifest: {result.manifest_path}")
    return 0


def _run_index(config_path: str | None, *, rebuild: bool = False) -> int:
    try:
        config = load_config(config_path, require_api_key=False)
    except ConfigError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 2

    try:
        result = index_chunks(config, rebuild=rebuild)
    except (ChunkingError, IndexingError) as exc:
        print(f"Index error: {exc}", file=sys.stderr)
        return 1

    for warning in result.warnings:
        print(f"  WARN {warning}")

    action = "Rebuilt and indexed" if result.rebuilt else "Indexed"
    print(
        f"\n{action} {result.chunk_count} chunks into Chroma collection "
        f"'{result.collection_name}'."
    )
    print(f"Collection count: {result.collection_count}")
    print(f"Persist path: {result.persist_path}")
    print(
        f"Sample query: {result.sample_chunk_id} "
        f"({result.sample_source_url})"
    )
    return 0


def _run_retrieve(
    config_path: str | None,
    query: str,
    *,
    top_k: int | None = None,
) -> int:
    try:
        config = load_config(config_path, require_api_key=False)
    except ConfigError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 2

    try:
        result = Retriever(config).retrieve(query, top_k=top_k)
    except RetrievalError as exc:
        print(f"Retrieval error: {exc}", file=sys.stderr)
        return 1

    print(f"Query: {result.query}")
    print(f"Filters: {result.filters.as_dict()}")
    print(f"Low confidence: {result.low_confidence}")
    print(f"Retried without filters: {result.retry_without_filters}")
    print(f"Hits ({len(result.hits)}):")
    for hit in result.hits:
        print(
            f"  {hit.score:.3f}  {hit.chunk_id}  "
            f"{hit.scheme} / {hit.section}"
        )
    if not result.hits and result.fallback_source_url:
        print(f"Fallback source: {result.fallback_source_url}")
    print(f"Artifact: {result.artifact_path}")
    return 0


def _print_answer(result: AnswerResult) -> None:
    print(f"\n{result.answer}")
    print(f"\nStatus: {result.status}")
    if result.citation_url:
        print(f"Citation: {result.citation_url}")
    if result.last_updated:
        print(f"Last updated: {result.last_updated}")
    print(f"Request ID: {result.request_id}")
    if result.artifact_path:
        print(f"Answer artifact: {result.artifact_path}")
    if result.diagnostics.get("retrieval_artifact"):
        print(
            "Retrieval artifact: "
            f"{result.diagnostics['retrieval_artifact']}"
        )


def _run_ask(
    config_path: str | None,
    query: str,
    *,
    request_id: str | None = None,
) -> int:
    try:
        config = load_config(config_path, require_api_key=False)
    except ConfigError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 2

    try:
        result = Answerer(config).answer(query, request_id=request_id)
    except AnswerError as exc:
        print(f"Answer error: {exc}", file=sys.stderr)
        return 1

    _print_answer(result)
    return 0


def _run_chat(config_path: str | None) -> int:
    try:
        config = load_config(config_path, require_api_key=True)
    except ConfigError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 2

    try:
        answerer = Answerer(config)
    except Exception as exc:
        print(f"Answerer setup error: {exc}", file=sys.stderr)
        return 1

    print("Groww MF FAQ interactive test")
    print("Type a question and press Enter. Use 'exit' or 'quit' to stop.")
    print(f"Provider: {config.llm.provider} ({config.llm.model})")

    while True:
        try:
            query = input("\nQuestion: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nStopped.")
            return 0

        if not query:
            continue
        if query.lower() in {"exit", "quit", ":q"}:
            print("Stopped.")
            return 0

        try:
            result = answerer.answer(query)
        except AnswerError as exc:
            print(f"Answer error: {exc}", file=sys.stderr)
            continue

        _print_answer(result)


def _run_evaluate(
    config_path: str | None,
    *,
    golden_path: Path,
    refusal_path: Path,
    mock: bool = False,
) -> int:
    try:
        config = load_config(config_path, require_api_key=False)
    except ConfigError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 2

    try:
        cases = load_eval_cases(golden_path) + load_eval_cases(
            refusal_path
        )
    except EvaluationError as exc:
        print(f"Evaluation input error: {exc}", file=sys.stderr)
        return 2

    llm_client = MockLLM() if mock else None
    answerer = Answerer(config, llm_client=llm_client)
    if not mock and not api_key_available(answerer):
        print(
            "Missing LLM API key for live evaluation. Set "
            f"{config.llm.api_key_env} or run with --mock.",
            file=sys.stderr,
        )
        return 2

    results = evaluate_cases(answerer, cases)
    for result in results:
        failed = [
            name for name, ok in result.checks.items() if not ok
        ]
        marker = "PASS" if result.passed else "FAIL"
        print(
            f"  {marker}  {result.case_id:<4} "
            f"status={result.actual_status:<20} "
            f"expected={','.join(result.expected_status)}"
        )
        if failed:
            print(f"        failed checks: {', '.join(failed)}")

    passed = sum(1 for result in results if result.passed)
    report_path = (
        config.paths.artifacts_dir / "06_eval" / "evaluation_report.json"
    )
    write_report(results, report_path)
    print(f"\nEvaluation: {passed}/{len(results)} passed.")
    print(f"Report: {report_path}")
    return 0 if passed == len(results) else 1


def _run_config(config_path: str | None) -> int:
    try:
        config = load_config(config_path)
    except ConfigError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 2

    paths = config.paths
    print("Config OK")
    print(f"  app:        {config.app.name}")
    print(f"  sources:    {len(config.data.source_urls)} configured URLs")
    print(
        f"  chunking:   {config.chunking.strategy} "
        f"(max_tokens={config.chunking.max_tokens}, "
        f"overlap={config.chunking.overlap_tokens})"
    )
    print(
        f"  embedding:  {config.embedding.model} "
        f"(normalize={config.embedding.normalize}, "
        f"batch_size={config.embedding.batch_size})"
    )
    print(
        f"  vector_db:  {config.vector_db.provider} "
        f"collection={config.vector_db.collection} "
        f"path={config.vector_db.persist_path}"
    )
    print(
        f"  retrieval:  top_k={config.retrieval.top_k} "
        f"threshold={config.retrieval.similarity_threshold}"
    )
    print(
        f"  llm:        {config.llm.provider}/{config.llm.model} "
        f"(temperature={config.llm.temperature}, "
        f"max_tokens={config.llm.max_tokens})"
    )
    print(f"  api_key:    {config.llm.api_key_env} is set")
    print(f"  artifacts:  {paths.artifacts_dir}")
    print(f"  chunks:     {paths.chunks_dir}")
    print(f"  embeddings: {paths.embeddings_dir}")
    print(f"  retrieval:  {paths.retrieval_dir}")
    print(f"  answers:    {paths.answers_dir}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="src.cli",
        description="Groww mutual fund FAQ assistant pipeline.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    config_parser = subparsers.add_parser(
        "config",
        help="Validate config.yaml and the configured LLM API key.",
    )
    config_parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to config.yaml (defaults to project root config.yaml).",
    )
    config_parser.add_argument("--verbose", action="store_true")

    load_parser = subparsers.add_parser(
        "load",
        help="Load and validate the scraped raw documents.",
    )
    load_parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to config.yaml (defaults to project root config.yaml).",
    )
    load_parser.add_argument("--verbose", action="store_true")

    chunk_parser = subparsers.add_parser(
        "chunk",
        help="Chunk the loaded documents into artifacts/02_chunks.",
    )
    chunk_parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to config.yaml (defaults to project root config.yaml).",
    )
    chunk_parser.add_argument("--verbose", action="store_true")

    embed_parser = subparsers.add_parser(
        "embed",
        help="Embed chunks into artifacts/03_embeddings.",
    )
    embed_parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to config.yaml (defaults to project root config.yaml).",
    )
    embed_parser.add_argument("--verbose", action="store_true")

    index_parser = subparsers.add_parser(
        "index",
        help="Upsert embeddings into the configured Chroma collection.",
    )
    index_parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Delete and recreate the collection before indexing.",
    )
    index_parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to config.yaml (defaults to project root config.yaml).",
    )
    index_parser.add_argument("--verbose", action="store_true")

    ask_parser = subparsers.add_parser(
        "ask",
        help="Answer a question with retrieval, guardrails, and the LLM.",
    )
    ask_parser.add_argument("query", help="Question to answer.")
    ask_parser.add_argument(
        "--request-id",
        default=None,
        help="Optional request ID for retrieval and answer artifacts.",
    )
    ask_parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to config.yaml (defaults to project root config.yaml).",
    )
    ask_parser.add_argument("--verbose", action="store_true")

    chat_parser = subparsers.add_parser(
        "chat",
        help="Interactively type questions and test live answers.",
    )
    chat_parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to config.yaml (defaults to project root config.yaml).",
    )
    chat_parser.add_argument("--verbose", action="store_true")

    evaluate_parser = subparsers.add_parser(
        "evaluate",
        help="Run golden factual and refusal cases against the answerer.",
    )
    evaluate_parser.add_argument(
        "--golden",
        type=Path,
        default=PROJECT_ROOT / "eval" / "golden_qa.yaml",
        help="Path to golden factual cases.",
    )
    evaluate_parser.add_argument(
        "--refusals",
        type=Path,
        default=PROJECT_ROOT / "eval" / "refusal_cases.yaml",
        help="Path to refusal and edge cases.",
    )
    evaluate_parser.add_argument(
        "--mock",
        action="store_true",
        help="Use a deterministic offline LLM instead of a live provider.",
    )
    evaluate_parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to config.yaml (defaults to project root config.yaml).",
    )
    evaluate_parser.add_argument("--verbose", action="store_true")

    retrieve_parser = subparsers.add_parser(
        "retrieve",
        help="Retrieve the top matching chunks for a question.",
    )
    retrieve_parser.add_argument("query", help="Question to retrieve chunks for.")
    retrieve_parser.add_argument(
        "--top-k",
        type=int,
        default=None,
        help="Override retrieval.top_k from config.yaml.",
    )
    retrieve_parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to config.yaml (defaults to project root config.yaml).",
    )
    retrieve_parser.add_argument("--verbose", action="store_true")

    scrape_parser = subparsers.add_parser(
        "scrape", help="Scrape the five configured Groww pages."
    )
    scrape_parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to config.yaml (defaults to project root config.yaml).",
    )
    scrape_parser.add_argument("--verbose", action="store_true")

    ingest_parser = subparsers.add_parser(
        "ingest",
        help="Run the full ingestion pipeline: scrape, chunk, embed, index.",
    )
    ingest_parser.add_argument(
        "--raw-only",
        action="store_true",
        help="Only scrape and store raw documents and HTML snapshots.",
    )
    ingest_parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Delete and recreate the Chroma collection before indexing.",
    )
    ingest_parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to config.yaml (defaults to project root config.yaml).",
    )
    ingest_parser.add_argument("--verbose", action="store_true")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _configure_logging(getattr(args, "verbose", False))

    config_path = str(args.config) if args.config else None

    if args.command == "config":
        return _run_config(config_path)

    if args.command == "load":
        return _run_load(config_path)

    if args.command == "chunk":
        return _run_chunk(config_path)

    if args.command == "embed":
        return _run_embed(config_path)

    if args.command == "index":
        return _run_index(config_path, rebuild=args.rebuild)

    if args.command == "evaluate":
        return _run_evaluate(
            config_path,
            golden_path=args.golden,
            refusal_path=args.refusals,
            mock=args.mock,
        )

    if args.command == "retrieve":
        return _run_retrieve(
            config_path,
            args.query,
            top_k=args.top_k,
        )

    if args.command == "ask":
        return _run_ask(
            config_path,
            args.query,
            request_id=args.request_id,
        )

    if args.command == "chat":
        return _run_chat(config_path)

    if args.command == "scrape":
        return _run_scrape(config_path)

    if args.command == "ingest":
        if args.raw_only:
            return _run_scrape(config_path)

        stages = (
            ("scrape", lambda: _run_scrape(config_path)),
            ("chunk", lambda: _run_chunk(config_path)),
            ("embed", lambda: _run_embed(config_path)),
            (
                "index",
                lambda: _run_index(config_path, rebuild=args.rebuild),
            ),
        )
        for stage_name, stage in stages:
            code = stage()
            if code != 0:
                print(
                    f"Ingestion stopped during {stage_name}.",
                    file=sys.stderr,
                )
                return code
        return 0

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
