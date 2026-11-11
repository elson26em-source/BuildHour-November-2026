from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from src.cli import main
from src.config.loader import (
    PROJECT_ROOT,
    ConfigError,
    load_config,
    resolve_api_key,
)

CONFIG_PATH = PROJECT_ROOT / "config.yaml"


def _write_config(tmp_path: Path, mutate=None) -> Path:
    raw = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    if mutate is not None:
        mutate(raw)
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    return path


def _isolated_root(tmp_path: Path) -> Path:
    shutil.copy(CONFIG_PATH, tmp_path / "config.yaml")
    return tmp_path


def test_load_config_with_api_key(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    root = _isolated_root(tmp_path)

    config = load_config(root / "config.yaml", project_root=root)

    assert len(config.data.source_urls) == 5
    assert config.data.follow_internal_links is False
    assert config.chunking.strategy == "section_aware"
    assert config.chunking.max_tokens == 450
    assert config.chunking.overlap_tokens == 50
    assert config.embedding.model == "sentence-transformers/all-MiniLM-L6-v2"
    assert config.vector_db.collection == "groww_mf_faq"
    assert config.retrieval.top_k == 5
    assert config.llm.provider == "groq"
    assert config.llm.api_key_env == "GROQ_API_KEY"
    assert resolve_api_key(config) == "test-key"
    assert config.paths.chunks_dir == (root / "artifacts/02_chunks").resolve()
    assert config.paths.answers_dir == (root / "artifacts/05_answers").resolve()


def test_missing_api_key_fails_fast(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    root = _isolated_root(tmp_path)

    with pytest.raises(ConfigError, match="GROQ_API_KEY"):
        load_config(root / "config.yaml", project_root=root)


def test_api_key_not_required_for_scraping(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    root = _isolated_root(tmp_path)

    config = load_config(
        root / "config.yaml", project_root=root, require_api_key=False
    )

    assert resolve_api_key(config) is None


def test_invalid_source_count_fails(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "test-key")

    def mutate(raw: dict) -> None:
        raw["data"]["source_urls"] = raw["data"]["source_urls"][:4]

    path = _write_config(tmp_path, mutate)
    with pytest.raises(ConfigError, match="exactly 5 URLs"):
        load_config(path, project_root=tmp_path)


def test_follow_internal_links_rejected(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "test-key")

    def mutate(raw: dict) -> None:
        raw["data"]["follow_internal_links"] = True

    path = _write_config(tmp_path, mutate)
    with pytest.raises(ConfigError, match="follow_internal_links"):
        load_config(path, project_root=tmp_path)


def test_invalid_threshold_fails(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "test-key")

    def mutate(raw: dict) -> None:
        raw["retrieval"]["similarity_threshold"] = 1.5

    path = _write_config(tmp_path, mutate)
    with pytest.raises(ConfigError, match="similarity_threshold"):
        load_config(path, project_root=tmp_path)


def test_unsupported_llm_provider_fails(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "test-key")

    def mutate(raw: dict) -> None:
        raw["llm"]["provider"] = "unknown"

    path = _write_config(tmp_path, mutate)
    with pytest.raises(ConfigError, match="llm.provider"):
        load_config(path, project_root=tmp_path)


def test_config_command_missing_key_returns_error(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    root = _isolated_root(tmp_path)

    exit_code = main(["config", "--config", str(root / "config.yaml")])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "Missing API key" in captured.err
    assert "GROQ_API_KEY" in captured.err


def test_cli_help_exits_zero(capsys) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--help"])

    assert excinfo.value.code == 0
    assert "Groww mutual fund FAQ assistant" in capsys.readouterr().out
