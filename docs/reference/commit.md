# commit

Generate a [Conventional Commits v1.0.0](https://www.conventionalcommits.org/) message for the currently staged changes via a local LLM.

## Synopsis

```bash
fobis commit [options]
```

## Options

| Option | Short | Description |
|--------|-------|-------------|
| `--backend TEXT` | `-b` | LLM backend: `ollama` (default) or `openai` |
| `--url TEXT` | `-u` | Base URL of the LLM server (default: `http://localhost:11434`) |
| `--model TEXT` | `-m` | Model identifier (default: `qwen3-coder:30b-a3b-q4_K_M`) |
| `--max-diff INT` | | Maximum staged-diff characters sent to the model (default: 12 000) |
| `--apply` | | Run `git commit` with the generated message after interactive review |
| `--config PATH` | `-c` | Path to a custom FoBiS user config file |
| `--show-config` | | Print the effective LLM configuration and exit |
| `--init-config` | | Create a commented default config file and exit |

## Description

`fobis commit` reads the currently staged changes (`git diff --cached`), the recent commit history (last 15 commits, used as a style reference), and the current branch name, then sends all this context to a local LLM to generate a well-formed commit message following the Conventional Commits specification.

The generated message is printed to standard output. Passing `--apply` prompts for confirmation and then runs `git commit -m <message>` automatically.

No network access to external APIs is required — the LLM runs locally via [Ollama](https://ollama.com) or any OpenAI-compatible server (LM Studio, vLLM, llama.cpp, etc.).

## Backends

### `ollama` (default)

Calls the Ollama native streaming chat API at `{url}/api/chat`. Requires Ollama to be running locally.

```bash
# Install Ollama: https://ollama.com
# Pull a model:
ollama pull qwen3-coder:30b-a3b-q4_K_M

# Run fobis commit (Ollama default, no extra flags needed):
fobis commit
```

### `openai`

Calls any OpenAI-compatible endpoint at `{url}/v1/chat/completions`. Covers:

- [LM Studio](https://lmstudio.ai) — default URL: `http://localhost:1234`
- [llama.cpp server](https://github.com/ggerganov/llama.cpp) — default URL: `http://localhost:8080`
- [vLLM](https://docs.vllm.ai) — default URL: `http://localhost:8000`
- Any cloud proxy exposing the OpenAI API

```bash
# LM Studio example:
fobis commit --backend openai --url http://localhost:1234 --model llama-3.2-3b
```

Note: Ollama also exposes an OpenAI-compatible endpoint at `/v1/chat/completions`, so `--backend openai --url http://localhost:11434` works with Ollama too.

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
# LLM backend: "ollama" (native API) or "openai" (any OpenAI-compatible endpoint)
# backend = ollama

# Base URL of the LLM server (no trailing slash)
# url = http://localhost:11434

# Model to use for commit-message generation
# model = qwen3-coder:30b-a3b-q4_K_M

# Maximum staged-diff characters sent to the model (long diffs are truncated)
# max_diff_chars = 12000
```

**Priority:** CLI flags → config file → hardcoded defaults.

Inspect effective settings at any time:

```bash
fobis commit --show-config
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
fobis commit --backend openai --url http://localhost:1234 --model llama-3.2-3b-instruct
```

### Use a custom config file

```bash
fobis commit --config ~/work/fobis-work.ini
```

## See also

- [LLM Commit Messages — Advanced Guide](/advanced/commit) — setup, tips, and worked examples
- [Claude Code skill](/guide/claude-skill) — AI-powered FoBiS assistance inside your editor
