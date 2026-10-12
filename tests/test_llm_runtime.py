"""Tests for the managed runtime: pins, install (on synthetic archives), resolution, the llama-server lifecycle
(against a stub server), the managed provider and the ``fobis llm runtime/ask/doctor`` commands.

The stub is a small Python program speaking the part of the llama-server contract FoBiS relies on, checked
against the real b11308 binary: ``--host/--port/--api-key``, ``GET /health`` answering 503 while loading then
200, ``POST /v1/chat/completions`` requiring the bearer key and streaming server-sent events, ``--version``.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import signal
import subprocess
import sys
import tarfile
import textwrap
import time
import zipfile

import pytest
from typer.testing import CliRunner

from fobis.llm import ConfigError, DownloadError, RuntimeMissingError, ServerStartError, messages
from fobis.llm import pins as pins_module
from fobis.llm.managed import ManagedProvider
from fobis.llm.pins import ASSETS, PINNED_BUILD, Asset
from fobis.llm.runtime import RuntimeManager, available_variants, detect_variant, platform_key
from fobis.llm.server import LlamaServer

STUB = textwrap.dedent(
    """\
    import json, os, sys, time
    from http.server import BaseHTTPRequestHandler, HTTPServer

    args = sys.argv[1:]
    if "--version" in args:
        print("version: 0.5.0-dev (build 11308, commit stub)")
        sys.exit(0)
    opt = lambda name: args[args.index(name) + 1]
    mode = os.environ.get("STUB_MODE", "ok")
    state = os.environ.get("STUB_STATE", "")
    if state:
        with open(state, "a") as fh:
            fh.write(f"{os.getpid()}\\n")
    if mode == "crash":
        print("error: failed to load model", flush=True)
        sys.exit(3)
    if mode == "bind-once" and state and len(open(state).read().split()) == 1:
        print("couldn't bind HTTP server socket: address already in use", flush=True)
        sys.exit(1)
    started = time.monotonic()
    key = opt("--api-key")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            print("request", self.path, flush=True)

        def do_GET(self):
            ready = mode != "hang" and time.monotonic() - started > 0.3
            body = b'{"status":"ok"}' if ready else b'{"error":{"message":"Loading model","code":503}}'
            self.send_response(200 if ready else 503)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            request = json.loads(self.rfile.read(length))
            if self.headers.get("Authorization") != f"Bearer {key}":
                self.send_response(401)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if request.get("response_format"):
                answer = json.dumps({"type": "fix", "scope": "io", "breaking": False,
                                     "description": "close the unit", "body": "", "footers": []})
            else:
                answer = "ready " + request["messages"][-1]["content"][:20]
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for piece in (answer[: len(answer) // 2], answer[len(answer) // 2 :]):
                chunk = {"choices": [{"delta": {"content": piece}}]}
                self.wfile.write(f"data: {json.dumps(chunk)}\\n\\n".encode())
            self.wfile.write(b"data: [DONE]\\n\\n")
            print("slot print_timing: eval time = 10 ms / 5 tokens (2 ms per token, 500.00 tokens per second)",
                  flush=True)

    HTTPServer((opt("--host"), int(opt("--port"))), Handler).serve_forever()
    """
)


@pytest.fixture
def stub(tmp_path):
    """An executable llama-server stub."""
    path = tmp_path / "bin" / "llama-server"
    path.parent.mkdir()
    path.write_text(f"#!{sys.executable}\n{STUB}")
    path.chmod(0o755)
    return str(path)


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    try:  # a zombie is dead for our purpose
        with open(f"/proc/{pid}/stat") as handle:
            return handle.read().split()[2] != "Z"
    except OSError:
        return True


# ── platform and variants ──────────────────────────────────────────────────────


def test_platform_key_normalisation():
    assert platform_key("Linux", "x86_64") == ("linux", "x86_64")
    assert platform_key("Linux", "arm64") == ("linux", "aarch64")
    assert platform_key("Darwin", "aarch64") == ("darwin", "arm64")
    assert platform_key("Windows", "AMD64") == ("windows", "amd64")


def test_every_pin_has_a_sha256_and_the_pinned_build():
    for (os_name, _, variant), (main, cudart) in ASSETS.items():
        assert len(main.sha256) == 64 and PINNED_BUILD in main.name
        assert (cudart is not None) == variant.startswith("cuda")
        assert os_name in ("linux", "darwin", "windows")


def _smi(output: str):
    return lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, stdout=output)


def test_detect_variant():
    linux = ("linux", "x86_64")
    gpu13 = "| NVIDIA-SMI 580 Driver Version: 580 CUDA Version: 13.2 |"
    assert detect_variant(linux, which=lambda n: "/x/nvidia-smi", run=_smi(gpu13))[0] == "cuda13"
    gpu12 = "CUDA Version: 12.8"
    assert detect_variant(linux, which=lambda n: "/x/nvidia-smi", run=_smi(gpu12))[0] == "cuda12"
    assert detect_variant(linux, which=lambda n: None)[0] == "cpu"
    assert detect_variant(("linux", "aarch64"), which=lambda n: "/x", run=_smi(gpu12))[0] == "cpu"  # no cuda12
    assert detect_variant(("darwin", "arm64"))[0] == "metal"
    assert available_variants(("linux", "aarch64")) == ["cpu", "cuda13", "vulkan"]
    with pytest.raises(ConfigError, match=r"no llama\.cpp build"):
        detect_variant(("freebsd", "x86_64"))


# ── install from synthetic archives ────────────────────────────────────────────


def _tar(files: dict[str, bytes], links: dict[str, str] | None = None, top: str = "llama-b11308") -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tf:
        for name, data in files.items():
            info = tarfile.TarInfo(f"{top}/{name}" if top else name)
            info.size = len(data)
            info.mode = 0o644
            tf.addfile(info, io.BytesIO(data))
        for name, target in (links or {}).items():
            info = tarfile.TarInfo(f"{top}/{name}" if top else name)
            info.type = tarfile.SYMTYPE
            info.linkname = target
            tf.addfile(info)
    return buffer.getvalue()


class _Response(io.BytesIO):
    def __init__(self, data: bytes) -> None:
        super().__init__(data)
        self.headers = {"Content-Length": str(len(data))}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def release(monkeypatch, stub):
    """Fake release assets for linux/x86_64 cpu and cuda13, served by a fake urlopen."""
    with open(stub, "rb") as handle:
        server_script = handle.read()
    archives = {
        "llama-cpu.tar.gz": _tar(
            {"llama-server": server_script, "libggml.so.0": b"lib"}, {"libggml.so": "libggml.so.0"}
        ),
        "llama-cuda.tar.gz": _tar({"llama-server": server_script, "libggml-cuda.so": b"cuda"}),
        "cudart.tar.gz": _tar({"libcublas.so.13": b"cublas"}, top="cudart-llama-b11308-bin-ubuntu-cuda-13.4-x64"),
    }

    def table():
        return {
            ("linux", "x86_64", "cpu"): (Asset("llama-cpu.tar.gz", _sha(archives["llama-cpu.tar.gz"])), None),
            ("linux", "x86_64", "cuda13"): (
                Asset("llama-cuda.tar.gz", _sha(archives["llama-cuda.tar.gz"])),
                Asset("cudart.tar.gz", _sha(archives["cudart.tar.gz"])),
            ),
        }

    monkeypatch.setattr("fobis.llm.runtime.ASSETS", table())
    requested = []

    def urlopen(request, timeout=None):
        name = request.full_url.rsplit("/", 1)[-1]
        requested.append(request.full_url)
        data = archives.get(name)
        if data is None:
            raise OSError("no such asset")
        return _Response(data)

    return archives, urlopen, requested, lambda: monkeypatch.setattr("fobis.llm.runtime.ASSETS", table())


def test_install_verifies_extracts_and_records(tmp_path, release):
    _, urlopen, requested, _ = release
    manager = RuntimeManager(str(tmp_path), key=("linux", "x86_64"), urlopen=urlopen)
    runtime, reason = manager.install("cpu")
    assert reason == "requested" and runtime.name == f"{PINNED_BUILD}-cpu"
    assert requested == [f"{pins_module.RELEASES_URL}/{PINNED_BUILD}/llama-cpu.tar.gz"]
    assert runtime.binary == os.path.join(manager.root, f"{PINNED_BUILD}-cpu", "llama-server")  # flattened
    assert os.access(runtime.binary, os.X_OK) and "build 11308" in runtime.version
    assert os.readlink(os.path.join(runtime.directory, "libggml.so")) == "libggml.so.0"
    with open(os.path.join(runtime.directory, "runtime.json")) as handle:
        meta = json.load(handle)
    assert meta["assets"][0]["pinned"] and meta["variant"] == "cpu"
    assert [r.name for r in manager.installed()] == [f"{PINNED_BUILD}-cpu"]
    assert manager.resolve() == runtime.binary


def test_install_cuda_adds_the_cuda_runtime_next_to_the_binary(tmp_path, release):
    manager = RuntimeManager(str(tmp_path), key=("linux", "x86_64"), urlopen=release[1])
    runtime, _ = manager.install("cuda13")
    assert sorted(os.listdir(runtime.directory)) == [
        "libcublas.so.13",
        "libggml-cuda.so",
        "llama-server",
        "runtime.json",
    ]


def test_install_checksum_mismatch_leaves_nothing(tmp_path, release):
    archives, urlopen, _, _ = release
    archives["llama-cpu.tar.gz"] = archives["llama-cpu.tar.gz"][:-1] + b"x"  # pinned sha unchanged
    manager = RuntimeManager(str(tmp_path), key=("linux", "x86_64"), urlopen=urlopen)
    with pytest.raises(DownloadError, match="sha256"):
        manager.install("cpu")
    assert os.listdir(manager.root) == []


@pytest.mark.parametrize(
    ("files", "links", "top"),
    [({"../evil": b"x"}, None, ""), ({"llama-server": b"x"}, {"lib.so": "../../../etc/passwd"}, "llama-b11308")],
    ids=["dotdot-member", "symlink-out"],
)
def test_install_rejects_archives_escaping_the_directory(tmp_path, release, files, links, top):
    archives, urlopen, _, repin = release
    archives["llama-cpu.tar.gz"] = _tar(files, links, top=top)
    repin()
    manager = RuntimeManager(str(tmp_path), key=("linux", "x86_64"), urlopen=urlopen)
    with pytest.raises(DownloadError, match="outside"):
        manager.install("cpu")
    assert os.listdir(manager.root) == []


def test_install_zip_without_binary(tmp_path, release, monkeypatch):
    archives, urlopen, _, _ = release
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("ggml.dll", b"x")
    archives["win.zip"] = buffer.getvalue()
    monkeypatch.setattr(
        "fobis.llm.runtime.ASSETS", {("windows", "amd64", "cpu"): (Asset("win.zip", _sha(archives["win.zip"])), None)}
    )
    manager = RuntimeManager(str(tmp_path), key=("windows", "amd64"), urlopen=urlopen)
    with pytest.raises(DownloadError, match="no llama-server"):
        manager.install("cpu")


def test_install_non_pinned_build_needs_sha_or_trust(tmp_path, release):
    archives, urlopen, _, _ = release
    manager = RuntimeManager(str(tmp_path), key=("linux", "x86_64"), urlopen=urlopen)
    with pytest.raises(ConfigError, match="not pinned"):
        manager.install("cpu", build="b99999")
    with pytest.raises(ConfigError, match="CUDA runtime"):
        manager.install("cuda13", build="b99999", sha256="0" * 64)
    with pytest.raises(DownloadError, match="sha256"):
        manager.install("cpu", build="b99999", sha256="0" * 64)
    runtime, _ = manager.install("cpu", build="b99999", trust=True)  # trust on first use: hash recorded
    with open(os.path.join(runtime.directory, "runtime.json")) as handle:
        meta = json.load(handle)
    assert meta["build"] == "b99999" and meta["assets"][0]["pinned"] is False
    assert meta["assets"][0]["sha256"] == _sha(archives["llama-cpu.tar.gz"])
    with pytest.raises(ConfigError, match="no 'rocm' build"):
        manager.install("rocm")


def test_resolve_and_remove(tmp_path, release, stub, monkeypatch):
    manager = RuntimeManager(str(tmp_path), key=("linux", "x86_64"), urlopen=release[1])
    with pytest.raises(RuntimeMissingError, match="fobis llm runtime install --variant cuda13"):
        manager.resolve("pinned", "cuda13")
    with pytest.raises(RuntimeMissingError, match="not an executable"):
        manager.resolve(str(tmp_path / "nope"))
    assert manager.resolve(stub) == stub
    monkeypatch.setenv("PATH", os.path.dirname(stub))
    assert manager.resolve("PATH") == stub
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    with pytest.raises(RuntimeMissingError, match="PATH"):
        manager.resolve("PATH")
    manager.install("cpu")
    manager.install("cuda13")
    assert manager.resolve("pinned", "cuda13").endswith(f"{PINNED_BUILD}-cuda13/llama-server")
    assert manager.remove(f"{PINNED_BUILD}-cpu").variant == "cpu"
    with pytest.raises(RuntimeMissingError):
        manager.remove(f"{PINNED_BUILD}-cpu")


# ── server lifecycle against the stub ──────────────────────────────────────────


def _server(stub, tmp_path, **kwargs) -> LlamaServer:
    model = tmp_path / "m.gguf"
    model.write_bytes(b"GGUF")
    return LlamaServer(stub, str(model), log_path=str(tmp_path / "logs" / "server.log"), **kwargs)


def test_server_starts_waits_for_health_and_stops(stub, tmp_path):
    from fobis.llm import OpenAICompatProvider

    server = _server(stub, tmp_path, startup_timeout=10)
    waits = []
    server.start(on_wait=waits.append)
    assert waits, "the stub answers 503 first: start() must have waited"
    assert "--api-key" in server.command() and "--parallel" in server.command()
    answer = OpenAICompatProvider(server.url, "m", api_key=server.api_key).chat(messages("hello")).text
    assert answer == "ready hello"
    assert server.generation_speed() == 500.0
    pid = server.process.pid
    server.stop()
    assert not _alive(pid)


def test_server_rejects_requests_without_its_key(stub, tmp_path):
    from fobis.llm import OpenAICompatProvider, ProviderResponseError

    with _server(stub, tmp_path, startup_timeout=10) as server, pytest.raises(ProviderResponseError) as excinfo:
        OpenAICompatProvider(server.url, "m", api_key="wrong").chat(messages("x"))
    assert excinfo.value.status == 401


def test_server_crash_reports_the_log_tail(stub, tmp_path, monkeypatch):
    monkeypatch.setenv("STUB_MODE", "crash")
    with pytest.raises(ServerStartError, match=r"status 3(.|\n)*failed to load model"):
        _server(stub, tmp_path, startup_timeout=10).start()


def test_server_timeout_kills_the_process(stub, tmp_path, monkeypatch):
    monkeypatch.setenv("STUB_MODE", "hang")
    monkeypatch.setenv("STUB_STATE", str(tmp_path / "pids"))
    with pytest.raises(ServerStartError, match="not ready after 1 s"):
        _server(stub, tmp_path, startup_timeout=1).start()
    pid = int((tmp_path / "pids").read_text().split()[0])
    assert not _alive(pid)


def test_server_retries_when_the_port_was_taken(stub, tmp_path, monkeypatch):
    monkeypatch.setenv("STUB_MODE", "bind-once")
    monkeypatch.setenv("STUB_STATE", str(tmp_path / "pids"))
    with _server(stub, tmp_path, startup_timeout=10) as server:
        assert server._health() == 200
    assert len((tmp_path / "pids").read_text().split()) == 2


def test_sigterm_to_fobis_stops_the_server(stub, tmp_path):
    """A FoBiS process killed with SIGTERM takes its llama-server down with it (no orphan)."""
    (tmp_path / "m.gguf").write_bytes(b"GGUF")
    script = textwrap.dedent(
        f"""\
        import os, signal
        from fobis.llm.server import LlamaServer
        server = LlamaServer({stub!r}, {str(tmp_path / "m.gguf")!r}, log_path={str(tmp_path / "s.log")!r},
                             startup_timeout=10).start()
        print(server.process.pid, flush=True)
        os.kill(os.getpid(), signal.SIGTERM)
        """
    )
    done = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=60)
    assert done.returncode == 128 + signal.SIGTERM, done.stderr
    pid = int(done.stdout.split()[0])
    time.sleep(0.2)
    assert not _alive(pid)


# ── managed provider ───────────────────────────────────────────────────────────


def _install_stub(root: str, stub: str) -> None:
    directory = os.path.join(root, "runtime", f"{PINNED_BUILD}-cpu")
    os.makedirs(directory)
    with open(os.path.join(directory, "runtime.json"), "w") as handle:
        json.dump({"build": PINNED_BUILD, "variant": "cpu", "binary": stub, "version": "stub"}, handle)


def test_managed_provider_reuses_one_server_and_closes_it(tmp_path, stub):
    root = str(tmp_path / "llm")
    _install_stub(root, stub)
    model = tmp_path / "local.gguf"
    model.write_bytes(b"GGUF")
    status = []
    with ManagedProvider(str(model), root=root, on_status=status.append, startup_timeout=10) as provider:
        first = provider.chat(messages("one"))
        pid = provider.server.process.pid
        second = provider.chat(messages("two"), schema={"type": "object"})
        assert provider.server.process.pid == pid
    assert (first.text, first.provider) == ("ready one", "managed")
    assert json.loads(second.text)["description"] == "close the unit"
    assert status == ["Starting llama-server with local.gguf..."]
    assert not _alive(pid) and provider.server is None
    assert os.path.isfile(os.path.join(root, "logs", "llama-server.log"))


def test_managed_provider_names_every_missing_piece(tmp_path):
    provider = ManagedProvider("coder-7b", root=str(tmp_path))
    with pytest.raises(RuntimeMissingError) as excinfo:
        provider.chat(messages("x"))
    assert "fobis llm runtime install" in str(excinfo.value) and "fobis llm pull coder-7b" in str(excinfo.value)


def test_get_provider_builds_the_managed_provider():
    from fobis.llm import LLMConfig, get_provider

    provider = get_provider(LLMConfig(provider="managed", url="", model="coder-14b", n_ctx=4096, threads=2))
    assert isinstance(provider, ManagedProvider)
    assert (provider.model, provider.n_ctx, provider.threads) == ("coder-14b", 4096, 2)


# ── CLI ────────────────────────────────────────────────────────────────────────


@pytest.fixture
def cli_env(tmp_path, monkeypatch, stub):
    root = tmp_path / "llm"
    _install_stub(str(root), stub)
    model = tmp_path / "local.gguf"
    model.write_bytes(b"GGUF")
    (tmp_path / "xdg" / "fobis").mkdir(parents=True)
    (tmp_path / "xdg" / "fobis" / "config.ini").write_text(
        f"[llm]\nprovider = managed\nmodel = {model}\nstartup_timeout = 10\n"
    )
    monkeypatch.setenv("FOBIS_LLM_DIR", str(root))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    from fobis.cli import app

    return CliRunner(), app


def test_cli_runtime_list_and_remove(cli_env):
    runner, app = cli_env
    assert f"{PINNED_BUILD}-cpu" in runner.invoke(app, ["llm", "runtime", "list"]).output
    assert "Removed" in runner.invoke(app, ["llm", "runtime", "remove", f"{PINNED_BUILD}-cpu"]).output
    assert "No runtime installed" in runner.invoke(app, ["llm", "runtime", "list"]).output
    failed = runner.invoke(app, ["llm", "runtime", "remove", "nope"])
    assert failed.exit_code == 1 and "no installed runtime" in failed.output


def test_cli_ask_streams_the_answer(cli_env, tmp_path):
    runner, app = cli_env
    result = runner.invoke(app, ["llm", "ask", "hello there"])
    assert result.exit_code == 0 and "ready hello there" in result.output
    schema = tmp_path / "s.json"
    schema.write_text('{"type": "object"}')
    assert '"close the unit"' in runner.invoke(app, ["llm", "ask", "x", "--schema", str(schema)]).output
    assert runner.invoke(app, ["llm", "ask", "x", "--schema", str(tmp_path / "none.json")]).exit_code == 1


def test_cli_doctor(cli_env):
    runner, app = cli_env
    result = runner.invoke(app, ["llm", "doctor"])
    assert result.exit_code == 0, result.output
    assert "ok   sample     'ready Reply with the singl'" in result.output and "500 tokens/s" in result.output
    assert runner.invoke(app, ["llm", "doctor", "--no-sample"]).exit_code == 0


def test_cli_doctor_reports_missing_pieces(tmp_path, monkeypatch):
    monkeypatch.setenv("FOBIS_LLM_DIR", str(tmp_path / "empty"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    from fobis.cli import app

    result = CliRunner().invoke(app, ["llm", "doctor"])
    assert result.exit_code == 1
    assert "BAD  runtime" in result.output and "fobis llm pull coder-7b" in result.output


# ── opt-in: the real thing ─────────────────────────────────────────────────────


@pytest.mark.llm
@pytest.mark.skipif(not os.environ.get("FOBIS_TEST_LLM"), reason="downloads ~0.5 GB: set FOBIS_TEST_LLM=1")
def test_real_runtime_and_model(tmp_path):
    """Install the pinned CPU build, pull the smallest recommended model, get an answer constrained by a schema.

    Set ``FOBIS_TEST_LLM_DIR`` to reuse a store between runs instead of downloading into a temporary directory.
    """
    from fobis.llm.models import ModelStore

    root = os.environ.get("FOBIS_TEST_LLM_DIR") or str(tmp_path)
    manager = RuntimeManager(root)
    if not any(r.build == PINNED_BUILD and r.variant == "cpu" for r in manager.installed()):
        manager.install("cpu")
    ModelStore(root).pull("coder-0.5b")
    schema = {
        "type": "object",
        "properties": {"answer": {"type": "string", "enum": ["yes", "no"]}},
        "required": ["answer"],
        "additionalProperties": False,
    }
    with ManagedProvider("coder-0.5b", root=root, variant="cpu", n_ctx=2048, startup_timeout=300) as provider:
        reply = provider.chat(messages("Is Fortran column-major? Answer yes or no."), schema=schema, temperature=0.0)
        pid = provider.server.process.pid
    assert json.loads(reply.text)["answer"] in ("yes", "no")
    assert not _alive(pid)
