# LLM Commit Messages

`fobis commit` generates [Conventional Commits v1.0.0](https://www.conventionalcommits.org/) messages for your staged changes using a **local LLM** — no cloud account, no API key, no data leaving your machine.

## The problem it solves

Writing good Conventional Commits messages consistently is harder than it looks:

- Did this change deserve `feat` or `refactor`?
- What is the right scope — `cli`, `scaffold`, `fetcher`?
- The body should explain the *why*, not the *what* — but after spending an hour on the code, the *why* is obvious to you and easy to skip.
- The message should match the style of existing history so changelogs look coherent.

`fobis commit` sends the staged diff, the git stat summary, the current branch name, and the recent commit history to a local model. The model studies the history's style and produces a well-formed message following the same patterns.

## Setup

### Ollama (recommended)

[Ollama](https://ollama.com) is the easiest way to run local models. Install it once and pull any compatible model.

```bash
# Install Ollama (https://ollama.com/download)
curl -fsSL https://ollama.com/install.sh | sh

# Pull the default model used by fobis commit:
ollama pull qwen3-coder:30b-a3b-q4_K_M

# Or a smaller/faster alternative:
ollama pull qwen2.5-coder:7b
ollama pull llama3.2:3b
```

Verify Ollama is running:

```bash
ollama list          # should show the pulled model
curl http://localhost:11434/api/tags   # should return JSON
```

No extra configuration needed — `fobis commit` defaults to `backend=ollama`, `url=http://localhost:11434`.

### LM Studio

[LM Studio](https://lmstudio.ai) provides a GUI for downloading and serving models with an OpenAI-compatible API.

1. Download and install LM Studio
2. Download a model (e.g. `Qwen2.5-Coder-7B-Instruct`)
3. Start the local server on port 1234

Then configure FoBiS:

```bash
fobis commit --init-config
# Edit ~/.config/fobis/config.ini:
```

```ini
[llm]
backend = openai
url     = http://localhost:1234
model   = qwen2.5-coder-7b-instruct
```

### llama.cpp server

```bash
# Start llama.cpp server:
./llama-server -m model.gguf --port 8080

# Configure FoBiS:
fobis commit --backend openai --url http://localhost:8080 --model model
```

### vLLM

```bash
# Start vLLM:
python -m vllm.entrypoints.openai.api_server --model Qwen/Qwen2.5-Coder-7B-Instruct

# Configure FoBiS:
fobis commit --backend openai --url http://localhost:8000 --model Qwen/Qwen2.5-Coder-7B-Instruct
```

## Persisting configuration

Create the default config once:

```bash
fobis commit --init-config
# Created: /home/user/.config/fobis/config.ini
```

Edit it to match your setup:

```ini
[llm]
backend        = ollama
url            = http://localhost:11434
model          = qwen2.5-coder:7b
max_diff_chars = 12000
```

Verify the effective configuration:

```bash
fobis commit --show-config
# Config file : /home/user/.config/fobis/config.ini
#   [llm]
#   backend       = ollama
#   url           = http://localhost:11434
#   model         = qwen2.5-coder:7b
#   max_diff_chars= 12000
```

**Priority rule:** CLI flags always win over the config file, which wins over built-in defaults. This means you can keep a comfortable default in the config file and override per-run with `--model` or `--backend` without editing the file.

## Typical workflow

```bash
# 1. Stage your changes as usual
git add fobis/Scaffold.py fobis/scaffolds/manifest.ini

# 2. Generate the message (no writes, just print)
fobis commit

# 3. Review — if it looks right, commit using --apply
git add fobis/Scaffold.py fobis/scaffolds/manifest.ini
fobis commit --apply

# Or: copy-paste the generated message into git commit -m manually
```

The `--apply` flag prints the message, asks `Commit with this message? [y/N]`, and runs `git commit -m <message>` only if you confirm.

## Worked examples

The following examples show real staged changes from the FoBiS repository and the messages `fobis commit` produced.

### Simple single-file fix

**Staged:**
```
fobis/cli/_app.py | 2 +-
```

**Diff summary:** rename `_COMPLETION_FLAGS` to lowercase `_completion_flags` to satisfy ruff N806 (module-level constant name).

**Generated message:**
```
fix(cli): rename _COMPLETION_FLAGS to lowercase to satisfy ruff N806
```

A one-liner — the model correctly identified this as a fix (a linting violation), scoped it to `cli`, and produced a short subject with no body (the change is self-evident).

---

### New feature with meaningful body

**Staged:**
```
fobis/Scaffolder.py        | 96 +++++++++++++++++++++++-
fobis/scaffolds/manifest.ini |  12 ++-
fobis/scaffolds/templated/fpm.toml | 2 +
```

**Diff summary:** add `init-only` manifest category, auto-populate `fpm.toml` `[dependencies]` from fobos or git submodules.

**Generated message:**
```
feat(scaffold): add init-only category and auto-discover fpm dependencies

Introduce a third manifest category for project-specific files that
should be seeded once but never overwritten by sync or flagged as
OUTDATED by status. Apply it to fpm.toml and docs/.vitepress/config.mts.

Auto-populate fpm.toml [dependencies] from the fobos [dependencies]
section (tag/rev/branch pins preserved), falling back to .gitmodules
+ git submodule status when no fobos deps are present.
```

The model correctly:
- Chose `feat` over `refactor` (new capability, not just restructuring)
- Scoped to `scaffold` (the most affected component)
- Wrote a body explaining the *design decisions*, not just listing the changed files
- Kept body lines within 72 chars

---

### CI/boilerplate update — short message appropriate

**Staged:**
```
fobis/scaffolds/verbatim/.github/workflows/ci.yml | 37 ++++++-------
```

**Diff summary:** update ci.yml to trigger on all branches (not just master/develop), use `tags-ignore`, rename job.

**Generated message:**
```
ci(scaffold): update ci.yml boilerplate to match FLAP reference
```

A one-liner is exactly right here — CI config changes rarely need a body, and the model chose `ci` (not `chore` or `feat`) correctly.

---

### Multi-component refactor

**Staged:**
```
fobis/Commit.py       | 257 +++++++++++++++++++++++++
fobis/UserConfig.py   | 112 ++++++++++++++++
fobis/cli/commit.py   |  77 +++++++++++
fobis/fobis.py        |  54 +++++++++++
fobis/cli/__init__.py |   2 +-
```

**Generated message:**
```
feat(cli): add LLM-assisted commit-message generation

Introduce `fobis commit` to generate Conventional Commits messages for
staged changes via a local LLM. Supports the native Ollama API and any
OpenAI-compatible endpoint (LM Studio, vLLM, llama.cpp).

All LLM settings are configurable via ~/.config/fobis/config.ini with
CLI flags taking precedence. Use --apply to run git commit after an
interactive review, --show-config to inspect effective settings, and
--init-config to seed the config file with commented defaults.
```

For a large multi-file addition the model generates a complete message with an informative body — it correctly identified the primary scope as `cli` even though the changes span `Commit.py`, `UserConfig.py`, and `fobis.py`.

## Tips for better results

### Choose a code-oriented model

Commit messages require understanding code diffs. Models fine-tuned on code produce better results:

| Model | Size | Notes |
|-------|------|-------|
| `qwen3-coder:30b-a3b-q4_K_M` | 30B (MoE, ~3B active) | Default; excellent quality, fast |
| `qwen2.5-coder:7b` | 7B | Fast, good quality for most changes |
| `qwen2.5-coder:14b` | 14B | Better quality on complex diffs |
| `deepseek-coder-v2:16b` | 16B | Strong on code understanding |
| `llama3.2:3b` | 3B | Fastest, acceptable for simple changes |

### Increase `max_diff_chars` for large refactors

The default limit of 12 000 characters is enough for most changes. For large refactors that touch many files, the diff may be truncated:

```bash
fobis commit --max-diff 30000
```

Or set it permanently in the config file:

```ini
[llm]
max_diff_chars = 30000
```

### Stage atomic commits before running

`fobis commit` is most effective when the staged changes represent a single logical unit. If you have mixed changes staged, split them with `git add -p` first:

```bash
git add -p          # interactive hunk-by-hunk staging
fobis commit        # now the model sees a coherent change
```

### Reasoning models and `<think>` tags

Some models (e.g. `qwen3`) support extended reasoning by emitting `<think>…</think>` blocks before the final answer. FoBiS automatically strips these blocks — you only see the clean commit message.

To disable thinking mode for faster output (Ollama-specific option):

```bash
fobis commit --model qwen3-coder:30b-a3b-q4_K_M/no-think
```

### Running Ollama on a remote machine

If Ollama runs on a different host (e.g. a workstation with a GPU):

```ini
[llm]
backend = ollama
url     = http://192.168.1.100:11434
model   = qwen2.5-coder:14b
```

Or pass it per run:

```bash
fobis commit --url http://192.168.1.100:11434
```

## How it works internally

`fobis commit` builds a prompt with four sections:

```
- Branch: develop

## Staged changes (stat)
 fobis/Scaffolder.py | 96 ++++++++++++++++++++++
 ...

## Staged diff
diff --git a/fobis/Scaffolder.py ...
...

## Recent commits (style reference)
abc1234 feat(scaffold): add init-only category
def5678 ci(scaffold): update ci.yml boilerplate
...

Generate the semantic commit message for the staged changes above.
```

The system prompt contains the full Conventional Commits specification, type-selection rules with good/bad examples, scope-inference guidance, body-writing guidance ("explain the *why*"), changelog-readiness rules, and three real FoBiS commit messages as few-shot examples.

The response is streamed token-by-token, `<think>` blocks are stripped, and the final text is word-wrapped at 72 characters before display.

## Command reference

See [`commit` command](/reference/commit) for the full option reference.
