"""Tests for UserConfig — user-level LLM configuration."""

from __future__ import annotations

import pytest

from fobis.UserConfig import UserConfig


def test_defaults_with_no_file(tmp_path):
    cfg = UserConfig(path=str(tmp_path / "nonexistent.ini"))
    assert cfg.llm_backend == UserConfig.DEFAULT_BACKEND
    assert cfg.llm_url == UserConfig.DEFAULT_URL
    assert cfg.llm_model == UserConfig.DEFAULT_MODEL
    assert cfg.llm_max_diff_chars == UserConfig.DEFAULT_MAX_DIFF_CHARS
    assert cfg.llm_refine_passes == UserConfig.DEFAULT_REFINE_PASSES


def test_custom_values_from_file(tmp_path):
    cfg_path = tmp_path / "config.ini"
    cfg_path.write_text(
        "[llm]\n"
        "backend = openai\n"
        "url = http://localhost:1234\n"
        "model = gpt4\n"
        "max_diff_chars = 5000\n"
        "refine_passes = 2\n"
    )
    cfg = UserConfig(path=str(cfg_path))
    assert cfg.llm_backend == "openai"
    assert cfg.llm_url == "http://localhost:1234"
    assert cfg.llm_model == "gpt4"
    assert cfg.llm_max_diff_chars == 5000
    assert cfg.llm_refine_passes == 2


def test_partial_override_falls_back_to_defaults(tmp_path):
    cfg_path = tmp_path / "config.ini"
    cfg_path.write_text("[llm]\nbackend = openai\n")
    cfg = UserConfig(path=str(cfg_path))
    assert cfg.llm_backend == "openai"
    assert cfg.llm_url == UserConfig.DEFAULT_URL
    assert cfg.llm_model == UserConfig.DEFAULT_MODEL


def test_create_default_writes_file(tmp_path):
    cfg_path = tmp_path / "subdir" / "config.ini"
    cfg = UserConfig(path=str(cfg_path))
    cfg.create_default()
    assert cfg_path.exists()
    text = cfg_path.read_text()
    assert "[llm]" in text
    assert "backend" in text


def test_create_default_is_idempotent(tmp_path):
    cfg_path = tmp_path / "config.ini"
    cfg = UserConfig(path=str(cfg_path))
    cfg.create_default()
    original = cfg_path.read_text()
    cfg.create_default()  # second call must not overwrite
    assert cfg_path.read_text() == original


def test_show_returns_all_keys(tmp_path):
    cfg = UserConfig(path=str(tmp_path / "nonexistent.ini"))
    output = cfg.show()
    assert "backend" in output
    assert "url" in output
    assert "model" in output
    assert "max_diff_chars" in output
    assert "refine_passes" in output
