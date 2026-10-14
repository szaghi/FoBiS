# Local LLM runtime

With the `managed` provider (the default), FoBiS runs language models itself: it installs a pinned build of
[llama.cpp](https://github.com/ggml-org/llama.cpp)'s `llama-server`, starts it with a model from the
[local store](/ai/models) when a command needs it, and stops it when the command ends. There is no service to
install or keep running, no Python native extension, and the [standalone archive](#clusters-and-the-standalone-archive)
works the same way.

![fobis llm doctor and fobis commit with a local model](/gifs/12_llm_commit.gif)

## Setup

```bash
fobis llm runtime install     # the pinned llama.cpp build, in the variant this machine supports
fobis llm pull coder-7b       # a model: see fobis llm recommended
fobis llm doctor              # check everything, time a short answer
```

`doctor` on a laptop with the CPU build and the smallest model:

```text
ok   provider   managed  (model coder-0.5b)
ok   directory  /home/me/.fobis/llm
ok   platform   linux/x86_64, variants cpu, cuda12, cuda13, vulkan, rocm, sycl; auto -> cuda13 (NVIDIA driver supports CUDA 13.2)
ok   runtime    runtime/b11308-cpu/llama-server  (version: 0.5.0-dev (build 11308, commit feb9a3d6d))
ok   model      models/Qwen/Qwen2.5-Coder-0.5B-Instruct-GGUF/ebb20151.../qwen2.5-coder-0.5b-instruct-q4_k_m.gguf
ok   start      server ready in 0.6 s
ok   sample     'ready' in 0.1 s, 112 tokens/s
```

Generation speed measured with `doctor` on one machine (WSL2, NVIDIA GPU, CUDA 13.2 driver):

| Model | Build | Ready in | Tokens/s |
|-------|-------|----------|----------|
| `coder-0.5b` | `cpu` | 0.6 s | 112 |
| `coder-7b` | `cpu` | 5.0 s | 12 |
| `coder-7b` | `cuda13` | 2.4 s | 68 |

With `coder-7b` on the GPU, `fobis commit` takes a few seconds end to end.

Then the LLM features work with no further option: `fobis commit`, `fobis llm ask "..."`.

## The runtime

`fobis llm runtime install` downloads the release archive of the llama.cpp build pinned by this FoBiS
version (`b11308`), checks it against the sha256 recorded in FoBiS's source, unpacks it under
`~/.fobis/llm/runtime/<build>-<variant>/` and runs `llama-server --version`. CUDA variants also download the
CUDA runtime libraries that upstream publishes separately (about 0.4-0.6 GB).

| Variant | For | Platforms |
|---------|-----|-----------|
| `cpu` | any machine | Linux x86_64/arm64, macOS Intel, Windows x64/arm64 |
| `metal` | Apple silicon GPU | macOS arm64 |
| `cuda12`, `cuda13` | NVIDIA GPU (driver supporting that CUDA major version) | Linux x86_64, Windows x64 (`cuda13` also Linux arm64) |
| `vulkan` | AMD, Intel and NVIDIA GPUs through Vulkan | Linux, Windows x64 |
| `rocm` | AMD GPU with ROCm | Linux x86_64 |
| `sycl` | Intel GPU | Linux x86_64 |

Without `--variant`, FoBiS picks Metal on Apple silicon, CUDA when `nvidia-smi` reports a driver, otherwise
CPU, and prints why. Several variants can be installed side by side; `runtime_variant` in the configuration
chooses among them.

```bash
fobis llm runtime install --variant vulkan
fobis llm runtime list
fobis llm runtime remove b11308-cpu
```

**Other builds.** `--build bNNNNN` installs another llama.cpp build. FoBiS knows no hash for it, so pass the
archive's `--sha256`, or `--trust` to accept it on first use (the computed hash is recorded either way).

**Your own llama-server.** Set `runtime = PATH` (use the `llama-server` on PATH) or
`runtime = /path/to/llama-server` in the configuration. This is the way on systems where the release binaries
do not run, typically clusters whose glibc is older than the Ubuntu release builds need, or where the
site provides llama.cpp as a module.

## How a command uses the model

When a command needs the model, FoBiS:

1. checks that the runtime and the model are installed (if not, it stops with the `fobis llm` command to run:
   nothing is downloaded implicitly);
2. starts `llama-server` on `127.0.0.1`, on a free port, with a random API key generated for that process;
3. waits until the model is loaded (`startup_timeout`);
4. sends the requests, with JSON-Schema-constrained output where the feature needs structure (see below);
5. stops the server when the command ends, also on Ctrl-C or `kill` (unless it is the persistent server of
   `fobis llm serve`, see below).

**Bounded answers.** Every schema bounds its free text (`maxLength`, e.g. 600 characters for a claim) and its
lists (`maxItems`), and every request caps the answer's tokens. Without bounds a small model can loop inside one
string or list until the context is full: measured with `coder-0.5b` on a merge proposal, `"ours", "ours", ...`
for 2000 tokens and 30 s, then an answer that is not JSON; bounded, the grammar closes the value and the answer is
valid JSON in 3 s. Code fields (a merged text, a test program) are bounded by the token cap only. With
`provider = openai`, `maxLength` is not sent (OpenAI's strict structured outputs may reject it); `maxItems` and the
token cap still apply.

The server log is `~/.fobis/llm/logs/llama-server.log`; when the server fails to start, the error shows its
last lines.

**Shared machines.** The server listens on loopback only and refuses requests without its per-process key, so
other users of a login node cannot use it. Login nodes often forbid heavy computation: limit the CPU threads
with `threads`, or run on a compute node.

## Keeping the model loaded

Loading a model takes a few seconds (longer for large models on CPU). When you run several LLM commands in a
row, keep a server running:

```bash
fobis llm serve start          # the configured model (or --model coder-14b)
fobis commit                   # uses the running server: no start-up
fobis llm serve status
fobis llm serve stop
```

A command uses the running server only when it serves the same model; otherwise it starts its own, as usual.
The server keeps running after the terminal closes, until `serve stop` (or a reboot). Its address and key are
in `~/.fobis/llm/server.json`, readable by you only; its log is `~/.fobis/llm/logs/llama-server-persistent.log`.

## Configuration

In the `[llm]` section of `~/.config/fobis/config.ini` (`fobis commit --init-config` writes a commented
template):

| Key | Default | Meaning |
|-----|---------|---------|
| `provider` | `managed` | `managed`, `ollama` or `openai` |
| `model` | `coder-7b` | alias, `hf:<org>/<repo>[@<rev>]/<file>.gguf`, or a GGUF path |
| `runtime` | `pinned` | `pinned` (installed with `fobis llm runtime install`), `PATH`, or a path to `llama-server` |
| `runtime_variant` | `auto` | which installed variant to use |
| `n_ctx` | `16384` | context size in tokens (prompt plus answer) |
| `n_gpu_layers` | `auto` | layers offloaded to the GPU: a number, `auto` or `all` |
| `threads` | `0` | CPU threads; `0` lets llama.cpp choose |
| `startup_timeout` | `120` | seconds to wait for the model to load |

**Upgrading.** Before the managed runtime the default provider was Ollama. A `[llm]` section that sets `model`
or `url` without `provider` was written for Ollama and keeps using it. Add `provider = managed` to switch.

## Quick questions

```bash
fobis llm ask "What does the Fortran 'contiguous' attribute guarantee?"
fobis llm ask --schema answer.json "..."    # answer constrained to a JSON Schema
git diff | fobis llm ask -                  # prompt from standard input
```

`ask` uses the configured provider, so it is also a quick check of an Ollama or OpenAI-compatible setup
(`--provider`, `--model` override the configuration).

## Clusters and the standalone archive

Everything here works from `fobis.pyz` (`python3 fobis.pyz llm ...`): FoBiS adds no compiled Python
dependency. For a cluster without internet access, prepare the LLM directory on a connected machine and copy
it, as described for [models](/ai/models#clusters-without-internet-access); `FOBIS_LLM_DIR` points FoBiS to it.

**Clusters with an older glibc.** The pinned release binaries are built on a recent Ubuntu: on a cluster running
RHEL 8 (glibc 2.28) `llama-server` stops with ``version `GLIBC_2.34' not found`` (it needs glibc 2.38 and a
recent libstdc++), and `fobis llm runtime install` warns that `--version` failed. Build the same pinned release
from source on a compute node and point the configuration at it. On an NVIDIA A30 cluster (gcc 12 from
`gcc-toolset-12`, CUDA 12.3, cmake 3.26) the build job took 4 minutes on 16 cores:

```bash
git clone --depth 1 --branch b11308 https://github.com/ggml-org/llama.cpp
cmake -S llama.cpp -B llama.cpp/build -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=80 -DLLAMA_CURL=OFF \
  -DLLAMA_OPENSSL=OFF -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF -DCMAKE_BUILD_TYPE=Release
cmake --build llama.cpp/build --target llama-server -j 16
```

```ini
[llm]
runtime      = /path/to/llama.cpp/build/bin/llama-server
n_gpu_layers = 99
```

Run the LLM features inside a job on a GPU node (the login node usually has no GPU). There coder-7b started in
8 s, generated 29 tokens/s, and answered `fobis ask` in 3.4 s with `fobis llm serve start` keeping the server up
between commands; `fobis llm doctor` checks the whole chain.
