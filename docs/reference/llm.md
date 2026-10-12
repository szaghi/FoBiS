# `llm` command

Manage the local LLM harness. Guide: [Local models](/ai/models).

```bash
fobis llm <subcommand> [options]
```

| Subcommand | Description |
|---|---|
| `recommended` | List the curated models: alias, download size, licence, intended hardware. Downloads nothing |
| `pull MODEL` | Download a model into the store: resolves the revision to a commit, resumes interrupted downloads, verifies size and sha256, pulls every part of a split GGUF. Does nothing when the model is already stored |
| `list` | List the stored models: size, date, pinned spec; `--json` adds the file paths |
| `rm MODEL` | Delete a model's files and manifest entry; a spec without `@revision` deletes every stored revision |

`MODEL` is an alias of `recommended` (`coder-7b`) or a spec `hf:<org>/<repo>[@<revision>]/<file>.gguf`.

## Environment

| Variable | Effect |
|---|---|
| `FOBIS_LLM_DIR` | Root of the LLM directory (default `~/.fobis/llm`); models live in its `models/` subdirectory |
| `HF_TOKEN` | Hugging Face access token for gated repositories; sent to the Hub only, never to the CDN it redirects downloads to |
| `HF_ENDPOINT` | Hub base URL (default `https://huggingface.co`), for mirrors |

## Exit status

`0` on success; `1` with an `Error:` message on failure (unknown model, network failure, gated repository
without token, checksum mismatch, not enough disk space).
