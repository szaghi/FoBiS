"""Tests for UserConfig — user-level LLM configuration."""

from __future__ import annotations

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
        "[llm]\nbackend = openai\nurl = http://localhost:1234\nmodel = gpt4\nmax_diff_chars = 5000\nrefine_passes = 2\n"
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
    assert cfg.llm_model == UserConfig.DEFAULT_MODELS["openai"]  # the default model follows the provider


def test_managed_settings_defaults_and_overrides(tmp_path):
    default = UserConfig(path=str(tmp_path / "none.ini"))
    assert (default.llm_provider, default.llm_model) == ("managed", "coder-7b")
    assert (default.llm_runtime, default.llm_runtime_variant, default.llm_n_gpu_layers) == ("pinned", "auto", "auto")
    assert (default.llm_n_ctx, default.llm_threads, default.llm_startup_timeout) == (16384, 0, 120.0)
    assert default.llm_model_for("ollama") == "qwen3-coder:30b-a3b-q4_K_M"
    cfg_path = tmp_path / "config.ini"
    cfg_path.write_text(
        "[llm]\nmodel = coder-14b\nruntime = PATH\nruntime_variant = cuda13\nn_ctx = 8192\nn_gpu_layers = all\n"
        "threads = 8\nstartup_timeout = 300\n"
    )
    cfg = UserConfig(path=str(cfg_path))
    assert (cfg.llm_model, cfg.llm_runtime, cfg.llm_runtime_variant) == ("coder-14b", "PATH", "cuda13")
    assert (cfg.llm_n_ctx, cfg.llm_n_gpu_layers, cfg.llm_threads, cfg.llm_startup_timeout) == (8192, "all", 8, 300.0)
    assert "runtime       = PATH (variant cuda13)" in cfg.show()


def test_create_default_writes_file(tmp_path):
    cfg_path = tmp_path / "subdir" / "config.ini"
    cfg = UserConfig(path=str(cfg_path))
    cfg.create_default()
    assert cfg_path.exists()
    text = cfg_path.read_text()
    assert "[llm]" in text
    assert "provider" in text


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
    assert "provider" in output
    assert "url" in output
    assert "model" in output
    assert "max_diff_chars" in output
    assert "refine_passes" in output


def test_settings_written_for_ollama_keep_ollama(tmp_path):
    """A [llm] section from before the managed runtime (model/url, no provider) keeps meaning Ollama."""
    for body in ("model = qwen3-coder:30b\n", "url = http://gpu-box:11434\n"):
        cfg_path = tmp_path / "config.ini"
        cfg_path.write_text("[llm]\n" + body)
        assert UserConfig(path=str(cfg_path)).llm_provider == "ollama"
    cfg_path.write_text("[llm]\nprovider = managed\nmodel = coder-14b\n")
    assert UserConfig(path=str(cfg_path)).llm_provider == "managed"
    cfg_path.write_text("[llm]\nmax_diff_chars = 5000\n")
    assert UserConfig(path=str(cfg_path)).llm_provider == "managed"
