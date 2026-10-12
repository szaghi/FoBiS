"""Tests for fobis.llm — the provider-agnostic LLM layer."""

from __future__ import annotations

import io
import json
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from fobis.llm import (
    ApiKeyError,
    Completion,
    ConfigError,
    FakeProvider,
    LLMConfig,
    LLMError,
    OllamaProvider,
    OpenAICompatProvider,
    ProviderResponseError,
    ProviderUnavailableError,
    get_provider,
    messages,
    resolve_api_key,
)
from fobis.llm.http import post_stream
from fobis.UserConfig import UserConfig

# ── post_stream ────────────────────────────────────────────────────────────────


def _urlopen_mock(lines: list[bytes]) -> MagicMock:
    ctx = MagicMock()
    ctx.__enter__.return_value = lines
    ctx.__exit__.return_value = False
    return ctx


def test_post_stream_ollama_format():
    lines = [
        b'{"message": {"content": "feat"}, "done": false}\n',
        b'{"message": {"content": "(cli)"}, "done": true}\n',
    ]
    with patch("urllib.request.urlopen", return_value=_urlopen_mock(lines)):
        assert post_stream("http://localhost", {}) == "feat(cli)"


def test_post_stream_openai_sse_format():
    lines = [
        b'data: {"choices": [{"delta": {"content": "fix"}}]}\n',
        b'data: {"choices": [{"delta": {"content": ": bug"}}]}\n',
        b"data: [DONE]\n",
    ]
    with patch("urllib.request.urlopen", return_value=_urlopen_mock(lines)):
        assert post_stream("http://localhost", {}) == "fix: bug"


def test_post_stream_openai_null_delta_content_is_skipped():
    lines = [
        b'data: {"choices": [{"delta": {"role": "assistant", "content": null}}]}\n',
        b'data: {"choices": [{"delta": {"content": "ok"}}]}\n',
        b"data: [DONE]\n",
    ]
    with patch("urllib.request.urlopen", return_value=_urlopen_mock(lines)):
        assert post_stream("http://localhost", {}) == "ok"


def test_post_stream_skips_blank_lines_and_invalid_json():
    lines = [b"\n", b"   \n", b"not-json\n", b'{"message": {"content": "ok"}, "done": true}\n']
    with patch("urllib.request.urlopen", return_value=_urlopen_mock(lines)):
        assert post_stream("http://localhost", {}) == "ok"


def test_post_stream_reports_each_token():
    lines = [b'{"message": {"content": "a"}}\n', b'{"message": {"content": "b"}, "done": true}\n']
    seen: list[str] = []
    with patch("urllib.request.urlopen", return_value=_urlopen_mock(lines)):
        post_stream("http://localhost", {}, on_token=seen.append)
    assert seen == ["a", "b"]


def test_post_stream_sends_payload_as_json():
    with patch("urllib.request.urlopen", return_value=_urlopen_mock([])) as mock_open:
        post_stream("http://localhost/x", {"model": "m"})
    request = mock_open.call_args.args[0]
    assert request.full_url == "http://localhost/x"
    assert json.loads(request.data) == {"model": "m"}
    assert request.get_header("Content-type") == "application/json"


def test_post_stream_sends_bearer_token_only_when_given():
    with patch("urllib.request.urlopen", return_value=_urlopen_mock([])) as mock_open:
        post_stream("http://localhost", {}, api_key="sk-test")
        post_stream("http://localhost", {})
    with_key, without_key = (call.args[0] for call in mock_open.call_args_list)
    assert with_key.get_header("Authorization") == "Bearer sk-test"
    assert without_key.get_header("Authorization") is None


def test_post_stream_url_error_raises_provider_unavailable():
    ctx = MagicMock()
    ctx.__enter__.side_effect = urllib.error.URLError("connection refused")
    ctx.__exit__.return_value = False
    with (
        patch("urllib.request.urlopen", return_value=ctx),
        pytest.raises(ProviderUnavailableError, match="cannot reach"),
    ):
        post_stream("http://localhost", {})


def test_post_stream_http_error_reports_status_and_body():
    err = urllib.error.HTTPError("http://x", 401, "Unauthorized", {}, io.BytesIO(b'{"error": "invalid api key"}'))
    with patch("urllib.request.urlopen", side_effect=err), pytest.raises(ProviderResponseError) as excinfo:
        post_stream("http://localhost", {})
    assert excinfo.value.status == 401
    assert "invalid api key" in str(excinfo.value)


def test_post_stream_timeout_raises_provider_unavailable():
    with (
        patch("urllib.request.urlopen", side_effect=TimeoutError("timed out")),
        pytest.raises(ProviderUnavailableError),
    ):
        post_stream("http://localhost", {})


def test_provider_errors_are_llm_errors():
    assert issubclass(ProviderUnavailableError, LLMError)
    assert issubclass(ProviderResponseError, LLMError)
    assert issubclass(ApiKeyError, ConfigError)
    assert issubclass(ConfigError, LLMError)


# ── messages ───────────────────────────────────────────────────────────────────


def test_messages_with_and_without_system():
    assert messages("p") == [{"role": "user", "content": "p"}]
    assert messages("p", system="s") == [{"role": "system", "content": "s"}, {"role": "user", "content": "p"}]


# ── providers ──────────────────────────────────────────────────────────────────


def test_openai_provider_endpoint_and_minimal_payload():
    provider = OpenAICompatProvider("http://localhost:1234/", "gpt4")
    assert provider.endpoint == "http://localhost:1234/v1/chat/completions"
    assert provider.payload(messages("p")) == {"model": "gpt4", "messages": messages("p"), "stream": True}


def test_openai_provider_payload_options_and_schema():
    schema = {"type": "object"}
    body = OpenAICompatProvider("http://x", "m").payload(
        messages("p"), schema=schema, temperature=0.0, seed=7, max_tokens=64
    )
    assert body["response_format"] == {
        "type": "json_schema",
        "json_schema": {"name": "response", "schema": schema, "strict": True},
    }
    assert (body["temperature"], body["seed"], body["max_tokens"]) == (0.0, 7, 64)


def test_ollama_provider_endpoint_and_minimal_payload():
    provider = OllamaProvider("http://localhost:11434/", "qwen")
    assert provider.endpoint == "http://localhost:11434/api/chat"
    assert provider.payload(messages("p")) == {"model": "qwen", "messages": messages("p"), "stream": True}


def test_ollama_provider_payload_options_and_schema():
    schema = {"type": "object"}
    body = OllamaProvider("http://x", "m").payload(messages("p"), schema=schema, temperature=0.0, seed=7, max_tokens=64)
    assert body["format"] == schema
    assert body["options"] == {"temperature": 0.0, "seed": 7, "num_predict": 64}


@pytest.mark.parametrize("cls", [OpenAICompatProvider, OllamaProvider])
def test_provider_chat_posts_and_wraps_completion(cls):
    provider = cls("http://x", "m", api_key="k", timeout=5)
    with patch("fobis.llm.http.urllib.request.urlopen") as mock_open:
        mock_open.return_value = _urlopen_mock([b'{"message": {"content": "hi"}, "done": true}\n'])
        completion = provider.chat(messages("p"))
    assert completion == Completion(text="hi", provider=cls.name, model="m")
    request = mock_open.call_args.args[0]
    assert request.full_url == provider.endpoint
    assert request.get_header("Authorization") == "Bearer k"
    assert mock_open.call_args.kwargs["timeout"] == 5


# ── FakeProvider ───────────────────────────────────────────────────────────────


def test_fake_provider_replays_script_and_records_calls():
    fake = FakeProvider(["one", "two"])
    assert fake.chat(messages("a")).text == "one"
    assert fake.chat(messages("b"), schema={"type": "object"}, temperature=0.0).text == "two"
    assert [c.messages[-1]["content"] for c in fake.calls] == ["a", "b"]
    assert fake.calls[1].schema == {"type": "object"}
    assert fake.calls[1].options["temperature"] == 0.0


def test_fake_provider_exhausted_script_raises():
    fake = FakeProvider(["only"])
    fake.chat(messages("a"))
    with pytest.raises(LLMError, match="no scripted reply"):
        fake.chat(messages("b"))


def test_fake_provider_callable_answers():
    fake = FakeProvider(lambda msgs: msgs[-1]["content"].upper())
    assert fake.chat(messages("abc")).text == "ABC"


def test_fake_provider_reports_token():
    seen: list[str] = []
    FakeProvider(["x"]).chat(messages("p"), on_token=seen.append)
    assert seen == ["x"]


# ── resolve_api_key ────────────────────────────────────────────────────────────


def test_resolve_api_key_none_without_configured_variable(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-must-not-leak")
    assert resolve_api_key(None) is None
    assert resolve_api_key("") is None


def test_resolve_api_key_reads_configured_variable(monkeypatch):
    monkeypatch.setenv("MY_LLM_KEY", "  sk-abc  ")
    assert resolve_api_key("MY_LLM_KEY") == "sk-abc"


def test_resolve_api_key_unset_variable_raises(monkeypatch):
    monkeypatch.delenv("MY_LLM_KEY", raising=False)
    with pytest.raises(ApiKeyError, match="MY_LLM_KEY"):
        resolve_api_key("MY_LLM_KEY")


# ── LLMConfig / get_provider ───────────────────────────────────────────────────


def test_llm_config_rejects_unknown_provider():
    with pytest.raises(ConfigError, match="unknown LLM provider 'olama'"):
        LLMConfig(provider="olama", url="http://x", model="m")


def test_llm_config_from_user_config_defaults(tmp_path):
    cfg = LLMConfig.from_user_config(UserConfig(path=str(tmp_path / "none.ini")))
    assert cfg == LLMConfig(provider="ollama", url=UserConfig.DEFAULT_URL, model=UserConfig.DEFAULT_MODEL)


def test_llm_config_cli_overrides_file(tmp_path):
    path = tmp_path / "config.ini"
    path.write_text("[llm]\nprovider = ollama\nurl = http://file\nmodel = filemodel\napi_key_env = FILE_KEY\n")
    cfg = LLMConfig.from_user_config(
        UserConfig(path=str(path)), provider="openai", url="http://cli", model="climodel", api_key_env="CLI_KEY"
    )
    assert cfg == LLMConfig(provider="openai", url="http://cli", model="climodel", api_key_env="CLI_KEY")


def test_llm_config_reads_former_backend_key(tmp_path):
    path = tmp_path / "config.ini"
    path.write_text("[llm]\nbackend = openai\n")
    assert LLMConfig.from_user_config(UserConfig(path=str(path))).provider == "openai"


def test_llm_config_provider_key_wins_over_backend_key(tmp_path):
    path = tmp_path / "config.ini"
    path.write_text("[llm]\nbackend = openai\nprovider = ollama\n")
    assert LLMConfig.from_user_config(UserConfig(path=str(path))).provider == "ollama"


def test_get_provider_builds_the_configured_class(monkeypatch):
    monkeypatch.setenv("K", "sk-1")
    openai = get_provider(LLMConfig(provider="openai", url="http://x/", model="m", api_key_env="K"))
    assert isinstance(openai, OpenAICompatProvider)
    assert (openai.url, openai.model, openai.api_key) == ("http://x", "m", "sk-1")
    ollama = get_provider(LLMConfig(provider="ollama", url="http://y", model="n"))
    assert isinstance(ollama, OllamaProvider)
    assert ollama.api_key is None


def test_get_provider_unset_key_variable_raises(monkeypatch):
    monkeypatch.delenv("NOPE", raising=False)
    with pytest.raises(ApiKeyError):
        get_provider(LLMConfig(provider="openai", url="http://x", model="m", api_key_env="NOPE"))
