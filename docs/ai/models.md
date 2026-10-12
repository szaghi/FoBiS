# Local models

FoBiS keeps a store of open-weight language models in GGUF format, downloaded from the
[Hugging Face Hub](https://huggingface.co), pinned to a commit and verified. The LLM features run on
these files locally: no code leaves your machine, and a cluster without internet access can use a store
prepared elsewhere.

Nothing is downloaded behind your back: only `fobis llm pull` downloads.

## Choosing a model

```bash
fobis llm recommended
```

```text
coder-0.5b       0.5 GB  Apache-2.0  smoke tests, laptops without GPU; weak at reasoning
coder-1.5b       1.1 GB  Apache-2.0  commit messages on CPU
coder-7b         4.7 GB  Apache-2.0  default choice: 8 GB GPU, or a recent CPU
coder-14b        9.0 GB  Apache-2.0  12-16 GB GPU
coder-30b-a3b   18.6 GB  Apache-2.0  24 GB GPU; mixture of experts (3B active), fast for its size
```

Each alias names one file of one commit of a Hub repository (4-bit `Q4_K_M` quantisations of
Qwen2.5-Coder and Qwen3-Coder), so `coder-7b` means the same bytes on every machine. All are under
the Apache-2.0 licence.

## Pulling

```bash
fobis llm pull coder-7b
fobis llm pull hf:Qwen/Qwen2.5-Coder-7B-Instruct-GGUF/qwen2.5-coder-7b-instruct-q4_k_m.gguf
fobis llm pull hf:org/repo@v1.2/subdir/model-q5_k_m.gguf
```

Any GGUF on the Hub can be pulled with a spec `hf:<org>/<repo>[@<revision>]/<file>.gguf`. A revision
can be a branch, a tag or a commit; without one, `main` is used. Either way FoBiS records the commit it
resolved to, so a later `main` does not silently replace your model.

What `pull` does:

- **Verifies.** It reads the size and sha256 of each file from the Hub and checks the download against
  them. A mismatching file is deleted, and the error says so.
- **Resumes.** An interrupted download (network failure, Ctrl-C) keeps its `.part` file; the next
  `pull` continues from where it stopped.
- **Handles split models.** For a model split in parts (`model-00001-of-00003.gguf`), name the first part
  and every part is pulled.
- **Checks disk space** before downloading.
- **Is idempotent.** Pulling a model already in the store does nothing.

```bash
fobis llm list            # what is in the store, with sizes and commits
fobis llm list --json     # the same with the file paths, for scripts
fobis llm rm coder-7b     # delete a model (a spec without @revision deletes every revision)
```

## Where the store lives

`~/.fobis/llm/models/`, or `$FOBIS_LLM_DIR/models/` when `FOBIS_LLM_DIR` is set:

```text
~/.fobis/llm/models/
  manifest.json                                  # spec -> files, sha256, sizes, date
  Qwen/Qwen2.5-Coder-7B-Instruct-GGUF/<commit>/qwen2.5-coder-7b-instruct-q4_k_m.gguf
```

## Clusters without internet access

Pull on a machine that has access, then copy the store; FoBiS needs nothing else:

```bash
FOBIS_LLM_DIR=/scratch/me/fobis-llm fobis llm pull coder-7b    # connected machine
rsync -a /scratch/me/fobis-llm/ cluster:/work/me/fobis-llm/
export FOBIS_LLM_DIR=/work/me/fobis-llm                        # on the cluster
fobis llm list
```

With the standalone archive the same commands run as `python3 fobis.pyz llm ...`.

## Gated repositories and mirrors

Some repositories require accepting a licence on the Hub. Accept it with your Hub account, create an
access token, and export it as `HF_TOKEN`. FoBiS sends the token to the Hub only: when the Hub redirects a
download to its content-delivery network, the token is not forwarded.

`HF_ENDPOINT` points FoBiS to a Hub mirror (for example an institutional proxy) instead of
`https://huggingface.co`.

## Using a stored model today

The managed runtime, with which FoBiS starts and stops llama.cpp itself, is the next step of the harness.
Until then, serve a stored model with any [llama.cpp](https://github.com/ggml-org/llama.cpp) build and
point the OpenAI-compatible provider at it:

```bash
llama-server -m "$(fobis llm list --json | python3 -c 'import json,sys; print(json.load(sys.stdin)[0]["path"])')" --port 8080
fobis commit --provider openai --url http://127.0.0.1:8080
```
