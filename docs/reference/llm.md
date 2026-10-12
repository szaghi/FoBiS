# `llm` command

Manage the local LLM harness. Guides: [Local LLM runtime](/ai/runtime), [Local models](/ai/models).

```bash
fobis llm <subcommand> [options]
```

| Subcommand | Description |
|---|---|
| `recommended` | List the curated models: alias, download size, licence, intended hardware. Downloads nothing |
| `pull MODEL` | Download a model into the store: resolves the revision to a commit, resumes interrupted downloads, verifies size and sha256, pulls every part of a split GGUF. Does nothing when the model is already stored |
| `list` | List the stored models: size, date, pinned spec; `--json` adds the file paths |
| `rm MODEL` | Delete a model's files and manifest entry; a spec without `@revision` deletes every stored revision |
| `runtime install` | Download, verify (pinned sha256) and install `llama-server`; `--variant` (default `auto`: detected), `--build bNNNNN` with `--sha256 HASH` or `--trust` for a build other than the pinned one |
| `runtime list` | List the installed builds and the variants available for this platform |
| `runtime remove NAME` | Delete an installed build (`<build>-<variant>`, as listed) |
| `ask PROMPT` | Ask the configured model; the answer streams to standard output. `-` reads the prompt from standard input; `--schema FILE` constrains the answer to a JSON Schema; `--system`, `--provider`, `--model` |
| `serve start` | Start a persistent `llama-server` with the configured model (`--model` to choose another); commands using the same model attach to it instead of starting their own |
| `serve status` | Show the persistent server (model, address, process, log); `--json` (without the key). Exit status 1 when none runs |
| `serve stop` | Stop the persistent server |
| `doctor` | Check provider, platform, runtime and model; with the managed provider start the model and time a short answer (`--no-sample` skips it). Exit status 1 when something is missing |

`MODEL` is an alias of `recommended` (`coder-7b`) or a spec `hf:<org>/<repo>[@<revision>]/<file>.gguf`.

## Environment

| Variable | Effect |
|---|---|
| `FOBIS_LLM_DIR` | Root of the LLM directory (default `~/.fobis/llm`): `models/`, `runtime/`, `logs/`, `server.json`. Paths inside are relative, so the directory can be moved or copied to another machine |
| `HF_TOKEN` | Hugging Face access token for gated repositories; sent to the Hub only, never to the CDN it redirects downloads to |
| `HF_ENDPOINT` | Hub base URL (default `https://huggingface.co`), for mirrors |

## Exit status

`0` on success; `1` with an `Error:` message on failure (unknown model, network failure, gated repository
without token, checksum mismatch, not enough disk space, runtime or model missing, server not starting).
