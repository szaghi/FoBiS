# `agents-md` command

Generate the build, test and verification instructions for coding agents (`AGENTS.md`) from the fobos and the
sources, between `<!-- fobis:begin agents-md -->` and `<!-- fobis:end agents-md -->`: the rest of the file is
kept. Guide: [Instructions for agents](/advanced/agents-md).

```bash
fobis agents-md [options]
```

| Option | Description |
|--------|-------------|
| `-o/--output FILE` | File to update, repeatable (e.g. `-o AGENTS.md -o CLAUDE.md`) [default: `AGENTS.md`] |
| `--check` | Write nothing; exit 1 when a file's block is stale (diff printed), absent, or the file missing |
| `--print` | Print the generated block on stdout; write nothing |
| `--mode M` | The mode whose sources and `-D` defines are analysed [default: the first mode] |
| `--json` | One JSON object: `facts`, `block`, and (without `--print`) `files` with each file's `path`, `status`, `diff` (see [JSON output](/advanced/json-output#fobis-agents-md-json)) |
| `-f/--fobos`, `--fci` | The fobos file |

File statuses: written `created`, `updated`, `appended` (the file had no block), `unchanged`; checked `current`,
`stale`, `no-block`, `missing`.

Exit code 0; 1 with `--check` when a file is not current; 2 for unbalanced or repeated markers, an unwritable
file, or an incorrect case/assessment declaration.
