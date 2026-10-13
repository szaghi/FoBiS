# commit

Generate a [Conventional Commits v1.0.0](https://www.conventionalcommits.org/) message for the currently staged changes via a local LLM.

## Synopsis

```bash
fobis commit [options]
```

## Options

| Option | Short | Description |
|--------|-------|-------------|
| `--provider TEXT` | `-b` | LLM provider: `managed` (default: llama.cpp run locally by FoBiS), `ollama` or `openai`. `--backend` is accepted as the former name |
| `--url TEXT` | `-u` | Base URL of the LLM server (default: `http://localhost:11434`) |
| `--api-key-env NAME` | | Name of the environment variable holding the API key, sent as `Authorization: Bearer <key>`; required by hosted endpoints. Without it no credentials are sent |
| `--model TEXT` | `-m` | Model identifier (default: `qwen3-coder:30b-a3b-q4_K_M`) |
| `--max-diff INT` | | Maximum staged-diff characters sent to the model (default: 12 000); truncation is file-boundary-aware — every file's metadata header is preserved |
| `--refine-passes INT` | | Critique-and-rewrite iterations after the initial draft (default: 0 = single pass); 1–3 recommended for small/fast models |
| `--apply` | | Run `git commit` with the generated message after interactive review |
| `--config PATH` | `-c` | Path to a custom FoBiS user config file |
| `--show-config` | | Print the effective LLM configuration and exit |
| `--init-config` | | Create a commented default config file and exit |
| `--show-facts` | | Print the facts of the staged change (scope candidates, Fortran line kinds, type hints) and exit; no model is run |
| `--no-facts` | | Do not compute the facts of the change: the scope is left free |
| `--json` | | With (or implying) `--show-facts`: the facts as one JSON object (see [JSON output](/advanced/json-output#fobis-commit-show-facts-json)) |

## Description

`fobis commit` reads the currently staged changes and sends them to a local LLM to generate a well-formed commit message following the Conventional Commits specification.

The prompt includes:

- **Complete file list** — `git diff --cached --name-status`, always authoritative regardless of diff size
- **Stat summary** — `git diff --cached --stat`
- **Staged diff** — up to `max_diff_chars`; truncated at file boundaries (metadata headers preserved for all files even when hunks are cut)
- **Recent commit history** — last 15 commits, used as a style reference
- **Branch name** — gives the model deployment context
- **Facts of the change** — scope candidates from the repository's history, Fortran lines classified as code, OpenMP/OpenACC directive or comment, type hints (see [Scope from facts](/advanced/commit#scope-from-facts))

The generated message is printed to standard output. Passing `--apply` prompts for confirmation and then runs `git commit -m <message>` automatically.

No network access to external APIs is required: by default FoBiS runs the model itself with llama.cpp ([Local LLM runtime](/ai/runtime)); [Ollama](https://ollama.com) and any OpenAI-compatible server (LM Studio, vLLM, llama-server, hosted services) work too.

The model answers a JSON object (type, scope, breaking, description, body, footers) constrained by a JSON Schema, and FoBiS builds the `type(scope)!: description` header itself, so the header syntax cannot be wrong. A server that rejects the schema (HTTP 400/422) gets the free-text request instead, cleaned as before.

## Backends

### `managed` (default)

FoBiS starts `llama-server` (llama.cpp) on loopback with a stored model, uses it for the command, and stops it. One-time setup:

```bash
fobis llm runtime install     # the pinned llama.cpp build, GPU variant detected
fobis llm pull coder-7b       # see: fobis llm recommended
fobis commit
```

See [Local LLM runtime](/ai/runtime) and [Local models](/ai/models).

### `ollama`

Calls the Ollama native streaming chat API at `{url}/api/chat`. Requires Ollama to be running locally.

```bash
# Install Ollama: https://ollama.com
# Pull a model:
ollama pull qwen3-coder:30b-a3b-q4_K_M

# Run fobis commit with Ollama:
fobis commit --provider ollama
```

### `openai`

Calls any OpenAI-compatible endpoint at `{url}/v1/chat/completions`. Covers:

- [LM Studio](https://lmstudio.ai) — default URL: `http://localhost:1234`
- [llama.cpp server](https://github.com/ggerganov/llama.cpp) — default URL: `http://localhost:8080`
- [vLLM](https://docs.vllm.ai) — default URL: `http://localhost:8000`
- Hosted OpenAI-compatible services (OpenAI, Mistral, OpenRouter, ...), with `--api-key-env`

```bash
# LM Studio example:
fobis commit --provider openai --url http://localhost:1234 --model llama-3.2-3b

# Hosted endpoint: the key is read from the named environment variable, never from the command line
export OPENAI_API_KEY=sk-...
fobis commit --provider openai --url https://api.openai.com --model gpt-4o-mini --api-key-env OPENAI_API_KEY
```

The key is sent only when a variable is named explicitly (`--api-key-env` or `api_key_env` in the config):
FoBiS never picks up `OPENAI_API_KEY` on its own, so a key cannot leak to a local server it was not meant for.
A hosted endpoint receives your staged diff.

Note: Ollama also exposes an OpenAI-compatible endpoint at `/v1/chat/completions`, so `--provider openai --url http://localhost:11434` works with Ollama too.

## User config file

All LLM settings can be persisted in `~/.config/fobis/config.ini` (XDG-aware: respects `$XDG_CONFIG_HOME`). Create the file with commented defaults:

```bash
fobis commit --init-config
```

The generated file looks like:

```ini
# FoBiS user configuration
# Location: /home/user/.config/fobis/config.ini
#
# All values shown are the defaults.  Uncomment and edit to override.

[llm]
# LLM provider: "managed" (fobis runs llama.cpp locally: fobis llm runtime install, fobis llm pull),
# "ollama" (native API) or "openai" (any OpenAI-compatible endpoint)
# (the former key name `backend` is still read)
# provider = managed

# Base URL of the LLM server (no trailing slash)
# url = http://localhost:11434

# Name of the environment variable holding the API key, sent as "Authorization: Bearer <key>".
# Needed by hosted endpoints (OpenAI, Mistral, ...); unset = no credentials are sent.
# api_key_env = OPENAI_API_KEY

# Model to use for commit-message generation
# model = qwen3-coder:30b-a3b-q4_K_M

# Maximum staged-diff characters sent to the model
# Truncation is file-boundary-aware: every file's metadata header is preserved.
# The complete file list is always sent separately and is never truncated.
# max_diff_chars = 12000

# Critique-and-rewrite passes after the initial draft (0 = single pass)
# Increase to 1-3 for small/fast models that produce shallow first drafts
# refine_passes = 0

[ecosystem]
# Directory the projects live in (relative entries of 'projects' are resolved against it)
# root = ~/fortran

# The managed projects: directory names under root, or paths; whitespace or newline separated
# projects = PENF FACE BeFoR64 StringiFor FLAP
# ... (theme and mode of the HTML dashboard)
```

The same file holds the `[ecosystem]` registry of [`fobis ecosystem`](/advanced/ecosystem), which
`fobis ecosystem add`/`remove` edit for you.

**Priority:** CLI flags → config file → hardcoded defaults.

Inspect effective settings at any time:

```bash
fobis commit --show-config
# Config file : /home/user/.config/fobis/config.ini
#   [llm]
#   provider      = managed
#   url           = http://localhost:11434
#   api_key_env   = (none)
#   model         = coder-7b
#   runtime       = pinned (variant auto)
#   n_ctx         = 16384
#   n_gpu_layers  = auto
#   threads       = 0
#   startup_timeout = 120
#   max_diff_chars= 12000
#   refine_passes = 0
```

## Examples

### Generate a message (print only)

```bash
git add fobis/Commit.py fobis/cli/commit.py
fobis commit
```

Output:

```
[ollama:qwen3-coder:30b-a3b-q4_K_M] Generating commit message…

feat(cli): add LLM-assisted commit-message generation

Introduce `fobis commit` to generate Conventional Commits messages for
staged changes via a local LLM. Supports the native Ollama API and any
OpenAI-compatible endpoint (LM Studio, vLLM, llama.cpp).
```

### Generate and commit in one step

```bash
git add fobis/Commit.py
fobis commit --apply
```

After printing the message:

```
Commit with this message? [y/N] y
[develop abc1234] feat(cli): add LLM-assisted commit-message generation
```

### Override model for a single run

```bash
fobis commit --model llama3.2
```

### Use LM Studio

```bash
fobis commit --provider openai --url http://localhost:1234 --model llama-3.2-3b-instruct
```

### Use a custom config file

```bash
fobis commit --config ~/work/fobis-work.ini
```

## See also

- [LLM Commit Messages — Advanced Guide](/advanced/commit) — setup, tips, and worked examples
- [Claude Code skill](/guide/claude-skill) — AI-powered FoBiS assistance inside your editor
