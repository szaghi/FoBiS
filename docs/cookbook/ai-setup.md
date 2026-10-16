---
title: Models, knowledge and agents
---

# Models, knowledge and agents

The setup behind the AI features: a language model run locally, the knowledge packs the answers are grounded on,
and the ways an external agent (Claude Code, Codex, any MCP client) uses FoBiS. The features themselves
(`--explain`, `ask`, `review --deep`, `testgen`, `commit`, `merge-assist`) are in [AI assistance](./ai).

How it works:

1. **The managed provider** (the default). FoBiS installs a pinned build of [llama.cpp](https://github.com/ggml-org/llama.cpp)'s
   `llama-server`, starts it on `127.0.0.1` when a command needs the model, and stops it when the command ends;
   `fobis llm serve start` keeps one running between commands instead. No service to install, no compiled Python
   dependency: the standalone `fobis.pyz` does the same.
2. **The model store.** Open-weight GGUF models from the Hugging Face Hub, pinned to a commit and checked against the
   Hub's sha256, in `~/.fobis/llm` (or `$FOBIS_LLM_DIR`), with the runtime, the logs and the server record.
3. **Nothing downloads implicitly.** Only `fobis llm runtime install` and `fobis llm pull` download; a command missing
   either stops with the command to run.
4. **Other providers.** `provider = ollama` or `provider = openai` (any OpenAI-compatible server or hosted service) in
   the `[llm]` section of the user configuration, `~/.config/fobis/config.ini`.
5. **Knowledge packs and agents need no model.** The packs are searched lexically; the MCP server and `agents-md` give
   an agent facts, never a model's answers.

Tutorial: [a model of your own](/tutorial/ai/01-model), [an agent under the gate](/tutorial/ai/09-agent),
[instructions for agents](/tutorial/quality/07-agents). Reference: [`llm`](/reference/llm), [`kb`](/reference/kb),
[`mcp`](/reference/mcp), [`agents-md`](/reference/agents-md), [user configuration](/reference/configuration).

## A local model in two commands

```bash
fobis llm runtime install     # the pinned llama-server, in the variant this machine supports
fobis llm pull coder-7b       # the default model, 4.7 GB
```

Every LLM feature then works with no further option. Without a `[llm]` section, the provider is `managed` and the
model `coder-7b`.

- **The runtime is pinned and verified.** `runtime install` downloads the llama.cpp release FoBiS is pinned to
  (`b11308`), checks it against the sha256 recorded in FoBiS's source, unpacks it under
  `~/.fobis/llm/runtime/<build>-<variant>/` and runs `llama-server --version`. A CUDA variant also downloads the CUDA
  runtime libraries upstream publishes separately (0.4 to 0.6 GB).
- **The variant is detected:** Metal on Apple silicon, `cuda13` or `cuda12` when `nvidia-smi` reports a driver
  supporting that CUDA version, otherwise `cpu`; the command prints why. `--variant` chooses another: `cpu`, `metal`,
  `cuda12`, `cuda13`, `vulkan` (AMD, Intel and NVIDIA GPUs), `rocm`, `sycl` (Intel GPUs), each where upstream builds it.

```bash
fobis llm runtime install --variant vulkan     # several variants can be installed side by side
fobis llm runtime list                         # installed builds, and the variants of this platform
fobis llm runtime remove b11308-cpu
fobis llm runtime install --build <bNNNNN> --sha256 <hash>   # another llama.cpp build: its hash, or --trust
```

With several variants installed, `runtime_variant` in `[llm]` chooses; `auto` takes the detected one when installed.

## Check the setup

```bash
fobis llm doctor              # provider, directory, platform, runtime, model; then starts the model and times an answer
fobis llm doctor --no-sample  # the checks only, nothing started
```

<<< @/examples/output/6-ai/01/doctor.measured.txt{console}

![fobis llm doctor and fobis commit with a local model](/gifs/12_llm_commit.gif)

A failed check prints `BAD` with the command that fixes it, and `doctor` exits 1. With the pinned runtime it also
checks that the installed build is the pinned one. With `ollama` or `openai`, it shows the server address (FoBiS does
not start that server) and times the sample answer there.

## Choose a model

<<< @/examples/output/6-ai/01/recommended.txt{console}

Each alias names one file of one commit of a Hub repository (4-bit `Q4_K_M` quantisations of Qwen2.5-Coder and
Qwen3-Coder, all Apache-2.0), so `coder-7b` is the same bytes on every machine. Set the model once:

```ini
[llm]
model = coder-14b
```

- **Size decides quality.** On FoBiS's own commit task the 0.5B and 1.5B models do not read the diff: they copy the
  prompt's examples. They prove the setup works; use `coder-7b` or larger for work.
- **A GPU decides speed.** Measured with `doctor` (WSL2, NVIDIA driver for CUDA 13.2): `coder-0.5b` on the CPU ready
  in 0.6 s and 112 tokens/s; `coder-7b` on the CPU 5.0 s and 12 tokens/s; `coder-7b` on `cuda13` 2.4 s and 68 tokens/s,
  where `fobis commit` takes a few seconds end to end. On an NVIDIA A30 node, `coder-7b` generated 29 tokens/s.
- **One command, another model:** `--model` on `fobis llm ask`, `fobis ask`, `fobis commit`, `fobis llm serve start`.

## Pull any GGUF model

```bash
fobis llm pull hf:Qwen/Qwen2.5-Coder-7B-Instruct-GGUF/qwen2.5-coder-7b-instruct-q4_k_m.gguf
fobis llm pull hf:org/repo@v1.2/subdir/model-q5_k_m.gguf   # a branch, tag or commit; main when omitted
fobis llm list                # the store: sizes, dates, pinned specs
fobis llm list --json         # with the file paths, for scripts or another llama.cpp
fobis llm rm coder-7b         # a spec without @revision removes every stored revision
```

The `model` key takes an alias, an `hf:` spec, or the path of a GGUF file.

- **The revision is pinned.** `pull` resolves the revision to a commit and records it: a later `main` does not
  replace your model.
- **Verified, resumable, idempotent.** The size and sha256 of each file come from the Hub; a mismatching file is
  deleted and the error says so. An interrupted download keeps its `.part` file and the next `pull` resumes it.
  Pulling a stored model does nothing. Disk space is checked first.
- **Split models:** name the first part (`model-00001-of-00003.gguf`) and every part is pulled.
- **Gated repositories:** accept the licence on the Hub, create an access token and export it as `HF_TOKEN`. FoBiS
  sends it to the Hub only: when the Hub redirects a download to its content-delivery network, the token is not
  forwarded.
- **Mirrors:** `HF_ENDPOINT` replaces `https://huggingface.co`, for an institutional proxy.
- **An Ollama tag is not a model of the store.** With the managed provider, `model = qwen2.5-coder:7b` stops with a
  message saying such a name needs `provider = ollama` or `openai`.

## Keep the server running

Loading a model takes seconds (longer for a large model on a CPU). For several LLM commands in a row:

```bash
fobis llm serve start         # the configured model (or --model coder-14b)
fobis commit                  # attaches to the running server: no start-up
fobis llm serve status        # model, address, process, log; exit 1 when none runs
fobis llm serve stop
```

<<< @/examples/output/6-ai/01/ask.measured.txt{console}

- **Same model only.** A command attaches to the persistent server when it serves the model the command needs;
  otherwise it starts its own, as usual, and leaves the persistent one alone.
- **It outlives the terminal,** until `serve stop` or a reboot: stop it on a shared machine. A second `serve start`
  is refused while one runs.
- **The record:** `~/.fobis/llm/server.json` (address, process, key), readable by you only; `serve status --json`
  prints it without the key, and an empty object, with exit 0, when none runs. The log is
  `~/.fobis/llm/logs/llama-server-persistent.log`; a per-command server logs to `logs/llama-server.log`, whose last
  lines the error shows when the server fails to start.

## Tune the managed server

```ini
[llm]
; context in tokens, prompt plus answer
n_ctx           = 16384
; layers offloaded to the GPU: a number, auto or all
n_gpu_layers    = auto
; CPU threads; 0 lets llama.cpp choose
threads         = 0
; seconds to wait for the model to load
startup_timeout = 120
```

- **Loopback only, one key per process.** The server listens on `127.0.0.1`, on a free port, and refuses requests
  without a random key generated for it. The key is on the server's command line: another user who can list your
  processes can read it.
- **Login nodes** usually forbid heavy computation: cap `threads`, or run on a compute node.
- **Stopped on exit.** A per-command server stops when the command ends, on Ctrl-C and on `kill`.
- **Bounded answers.** Every structured answer is constrained by a JSON Schema whose strings and lists are bounded,
  and every request caps its tokens: unbounded, `coder-0.5b` repeated `"ours", "ours", ...` for 30 s and returned
  invalid JSON; bounded, valid JSON in 3 s.

## Use Ollama or an OpenAI-compatible server

```ini
[llm]
provider = ollama
url      = http://localhost:11434
model    = qwen2.5-coder:7b
```

```ini
[llm]
; LM Studio, vLLM, a llama-server you started: FoBiS adds /v1/chat/completions
provider = openai
url      = http://localhost:1234
model    = qwen2.5-coder-7b-instruct
```

```ini
[llm]
; a hosted service: name the variable holding the key, never the key
provider    = openai
url         = https://api.openai.com
model       = gpt-4o-mini
api_key_env = OPENAI_API_KEY
```

```bash
fobis commit --init-config    # write the commented template, where the file is missing
fobis commit --show-config    # the settings in effect
fobis llm ask --provider ollama --model qwen2.5-coder:7b "Reply with one word: ready"
fobis commit --provider openai --url http://localhost:8080 --model model   # one run, nothing edited
```

The command line wins over the configuration, which wins over the defaults. `--url` and `--api-key-env` exist on
`fobis commit` only; `--config FILE` there reads another configuration file.

- **An old Ollama configuration keeps working.** Before the managed runtime the default was Ollama: a `[llm]` section
  setting `model` or `url` without `provider` still means Ollama. Add `provider = managed` to switch.
- **Set `url` and `model` with `openai`.** Their defaults are Ollama's: `http://localhost:11434` and
  `qwen3-coder:30b-a3b-q4_K_M`.
- **The key** is sent as `Authorization: Bearer <key>` only when `api_key_env` is set, and FoBiS stops with an error
  when the named variable is unset or empty. A key is never read from an implicit default variable.
- **A hosted service receives your code:** the staged diff, the sources and messages the feature sends.
- **No `maxLength` to `openai` servers:** OpenAI's strict structured outputs may reject it; the list bounds and the
  token cap still apply.
- **`backend`** is the former name of `provider` (key and `--backend`), still read.

## An offline cluster

Prepare the LLM directory where there is internet, copy it, point FoBiS at it:

```bash
FOBIS_LLM_DIR=/scratch/me/fobis-llm fobis llm pull coder-7b          # connected machine
FOBIS_LLM_DIR=/scratch/me/fobis-llm fobis llm runtime install --variant cuda12
rsync -a /scratch/me/fobis-llm/ cluster:/work/me/fobis-llm/
export FOBIS_LLM_DIR=/work/me/fobis-llm                               # on the cluster
fobis llm doctor
```

The paths inside the directory are relative, so it works wherever it lands. With the standalone archive the
commands are `python3 fobis.pyz llm ...`.

**An older glibc.** The pinned release binaries are built on a recent Ubuntu and need glibc 2.38 and a recent
libstdc++: on RHEL 8 (glibc 2.28) `llama-server` stops with ``version `GLIBC_2.34' not found``, and
`runtime install` warns that `--version` failed. Build the pinned release on a compute node and point `runtime` at it.
On an A30 cluster (gcc 12 from `gcc-toolset-12`, CUDA 12.3, cmake 3.26) it took 4 minutes on 16 cores:

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

- **`runtime = PATH`** runs the `llama-server` found on the PATH: a site module of llama.cpp.
- **Run on a GPU node,** inside a job: login nodes rarely have a GPU. There `coder-7b` started in 8 s and answered
  `fobis ask` in 3.4 s, with `fobis llm serve start` keeping the server up between commands.
- **The stored files are plain GGUF:** any llama.cpp build serves them (`fobis llm list --json` gives the paths).

## Ask the model directly

```bash
fobis llm ask "What does the Fortran 'contiguous' attribute guarantee?"
fobis llm ask --schema answer.json "Name the intrinsic"   # the answer constrained to a JSON Schema
git diff | fobis llm ask -                                # the prompt from standard input
fobis llm ask --system "Answer in one line." "What is an elemental procedure?"
```

The answer streams to standard output, from the configured provider: a quick check of any setup. It is the bare
model, with no grounding: for an answer cited from the packs and your sources, `fobis ask` in [AI assistance](./ai).

## Search the knowledge packs

```bash
fobis kb list                                        # installed packs: version, scope, sections, licence
fobis kb search "firstprivate associate copyin"      # the best sections, with their ids and scores
fobis kb search "reduction" --pack openacc -k 3      # one pack (repeatable), three results
fobis kb search "MPI_Init_thread thread level" --json
fobis kb show openacc:patterns#routine-for-device-callable-functions
fobis kb show openmp:ch07-data-environment#key-concepts -C 1   # with one neighbouring section on each side
fobis kb notice openmp                               # licence, attribution, source revision, NOTICE
```

The shipped packs, about 800 sections in all, CC-BY-4.0 by Stefano Zaghi:

- **`fortran-std`, `openmp`, `openacc`, `mpi`:** distilled references of Fortran 2023, OpenMP 6.0 with the November
  2025 errata, OpenACC 3.4 and MPI 5.0. Independent syntheses, not the standards: the normative text is the published
  standard. The OpenMP and MPI material is copied by permission of the OpenMP ARB and the University of Tennessee.
- **`hpc-practice`:** Fortran conventions and GPU/HPC pitfalls, many measured on production codes.
- **`compilers`, `libraries`, `numerics`:** gfortran, ifx/ifort and nvfortran behaviour (default optimisation, checks,
  floating-point models, precision promotion, stack, module files), MPI implementations and HDF5 from Fortran, and the
  error-assessment methods behind `fobis assess` and `fobis bench`. Every behaviour is measured on a small program
  with the version named, or cited; a test compiles a program with every flag the `compilers` pack names.

Every section has a stable id, `pack:document#section`. `fobis lint --explain ACC006` lists the sections behind a rule,
`fobis assess` names the section of each family's method, and `fobis ask`, `--explain` and `--deep` ground their
answers on them.

- **Retrieval is lexical,** no model and no embeddings: BM25 with heading words counted twice, plus a bonus for a
  query term that is one of the section's symbols (the directive, clause and routine names in its code spans, the
  constraint ids it cites). Name the exact thing: `firstprivate`, `mpi_isend`, `C1004`. Plurals are folded and a few
  synonyms expanded (`hang` finds deadlock); a paraphrase without the technical word finds little.
- **Exit status:** a search with no match prints `No match.` and exits 0; an unknown pack or section exits 1.
- **Reusing pack content** means keeping its attribution (CC-BY-4.0): `kb notice` prints it.

## Your own knowledge pack

Any markdown becomes a pack: notes, team conventions, a Claude skill directory.

```bash
fobis kb build ~/notes/gpu-lessons.md --name gpu-lessons --private      # yours only: no licence, never redistribute
fobis kb build docs/conventions/ --name team --license CC-BY-4.0 --attribution "ACME HPC group" --project
fobis kb build docs/conventions/ --name team --license CC-BY-4.0 --out build/team-pack   # build, do not install
fobis kb add path/to/pack-dir                        # install a pack built elsewhere (--project for the project)
fobis kb remove gpu-lessons                          # a user pack (--project for a project pack)
```

Packs are found in three places; on a name clash the narrowest wins:

1. **project:** `.fobis/kb/<name>/` of the current directory, versioned with the project;
2. **user:** `$XDG_CONFIG_HOME/fobis/kb/<name>/` (`~/.config/fobis/kb/` when unset);
3. **shipped:** inside FoBiS, which cannot be removed.

- **What the build keeps:** the content, one searchable section per heading, long sections split at paragraph
  boundaries. It drops what is addressed to an assistant: YAML front matter, sections such as "How to Use This
  Skill", lines telling the reader to consult a skill.
- **A licence is required** (`--license`, an SPDX id) unless `--private`; `--title`, `--attribution` and
  `--notice FILE` complete the pack's credits.
- **A pack directory** holds `pack.ini` (name, version, title, licence, attribution, source), an optional `NOTICE`,
  and `index.json` (the sections): copy it to share it, and `kb add` it.

## An MCP server for your agent

```bash
claude mcp add fobis -- fobis mcp                  # Claude Code, for the current project
```

Any client that launches stdio servers runs `fobis mcp` in the project directory, or with `--root`:

```json
{
  "mcpServers": {
    "fobis": { "command": "fobis", "args": ["mcp", "--root", "/path/to/project"] }
  }
}
```

With the standalone archive the command is `python3 fobis.pyz mcp`.

<<< @/examples/output/6-ai/09/tools.txt{console}

The agent gets facts and grounded context, not FoBiS's model answers: the agent is a model already, and a local one
answering for it would be a weaker one. So the tools return what FoBiS computes deterministically (findings, parsed
compiler messages, diagnoses, crash facts, API changes, the sources an answer would be grounded on: `ask_context`),
and `ask`, `lint --deep`, the model part of `--explain`, the `testgen` loop and commit messages stay command-line
features. The agent calling the gate after its edit:

<<< @/examples/output/6-ai/09/gate.txt{console}

- **Results are the commands' JSON documents,** as text and, with protocol 2025-06-18, as `structuredContent`. A
  failed build or test is a result, `"status": "error"` with why, not a tool error. `lint` and `review` return at
  most `max_findings` findings (default 200) and say when they truncated.
- **Annotations** tell the client what to confirm: `readOnlyHint` is false for the tools listed as `writes` above,
  `destructiveHint` true for `clean`, `idempotentHint` false for `fetch`, `openWorldHint` true for `fetch` and
  `ecosystem_status` (network). With Claude Code you approve each call unless you allow the tool.
- **The writing tools write build products, run directories and fetched dependencies, never sources or references:** `verify` never
  updates a reference, `bench` never records history, `modernize` never applies its fixes, `lint` with `fix_diff`
  returns a diff and writes nothing.
- **Slow tools:** `matrix` builds once per cell, `assess` once per variant. `test`, `case_run`, `verify`, `assess`,
  `diff_run`, `bench` and `profile` take `runner: slurm` to submit the runs as jobs: see [HPC and clusters](./hpc).
- **Resources:** `fobis://rules/{id}` (a lint rule's documentation, listed) and `fobis://kb/{id}` (a pack section, its
  id URL-encoded; `kb_search` gives each result's URI).
- **The protocol:** newline-delimited JSON-RPC 2.0 on standard input and output, versions 2025-06-18, 2025-03-26 and
  2024-11-05. The tools that read the fobos or build run `fobis ... --json` as a subprocess, so nothing they print
  reaches the protocol stream; rules and packs are answered in process. Checked with the official MCP Inspector
  2.10.1.

## AGENTS.md and CLAUDE.md from facts

An agent reads `AGENTS.md` (Claude Code: `CLAUDE.md`) before working on a project. Written by hand it goes stale: a
mode is renamed, the tests move, and the agent builds the wrong thing with confidence. `fobis agents-md` writes the
part that is fact, from the fobos and the sources:

```bash
fobis agents-md                    # write or update the generated block of AGENTS.md
fobis agents-md -o CLAUDE.md       # the same block in CLAUDE.md (repeatable: -o AGENTS.md -o CLAUDE.md)
fobis agents-md --print            # print the block, write nothing
fobis agents-md --print --json     # the facts, for scripts and agents
fobis agents-md --mode release     # the code facts of another mode's sources and defines
```

<<< @/examples/output/4-quality/07/print.txt{console}

- **Your text is kept.** The block sits between `<!-- fobis:begin agents-md -->` and `<!-- fobis:end agents-md -->`;
  a new file gets a title and the block, a file without markers gets it appended, an existing block is replaced in
  place. Unbalanced or repeated markers stop the command (exit 2).
- **Only the repository, never the machine.** Facts come from the fobos and the files git tracks or would track:
  no compiler versions, no fetched dependencies, no build directories, no date. The block is the same on a laptop and
  in CI, and a stale block is a real change.
- **Kinds as written:** `R8P`, not the number, with their decimal digits and the module that defines them, found when
  it is a project module's constant or the single module exporting it through only-lists.
- **Included files belong to their includer:** an `include`d file's procedures are not reported as lacking
  `implicit none`.
- **It describes, it does not judge.** Conventions it cannot measure (naming, error handling, the physics) belong in
  your hand-written part. One table row per mode: 94 rows for a 94-mode project. On a 251-file MPI + OpenACC code the
  facts took 2.2 s.

In CI, the block must be current:

```yaml
- run: fobis agents-md --check
```

Exit 0 when every file's block is current; 1 when one is stale (the diff is printed), has no block or does not exist;
2 for broken markers, an unwritable file or a fobos error. `--check --json` gives each file's status and diff. The MCP
tool `agents_md` gives the same facts and block. More in [Continuous integration](./ci).

## The Claude Code skill

The FoBiS skill teaches Claude Code how to use FoBiS: fobos syntax, every command and its options, dependencies,
library builds, the JSON output, the ecosystem, the diagnosis of common build errors. The MCP server lets the agent
run FoBiS; the two complement each other: install both.

```bash
mkdir -p ~/.claude/skills/fobis
curl -sSL https://raw.githubusercontent.com/szaghi/FoBiS/master/.claude/skills/fobis/SKILL.md \
  -o ~/.claude/skills/fobis/SKILL.md
```

Or copy `.claude/skills/fobis/SKILL.md` from a FoBiS checkout. Claude Code loads it for any question naming `fobos`,
FoBiS or a Fortran build, or on `/fobis`:

```text
/fobis write a fobos file with debug (-O0 -g -Wall) and release (-O3) modes, gfortran, sources in src/
/fobis Fatal Error: Module 'penf_b_size' not found: what is wrong?
/fobis add PENF v2.0.1 as a dependency
```

The skill is plain markdown: edit it for your workflow, or build it into a knowledge pack with `fobis kb build`.
