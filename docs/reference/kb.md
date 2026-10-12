# `kb` command

Search and manage the knowledge packs. Guide: [Knowledge packs](/ai/knowledge-packs).

```bash
fobis kb <subcommand> [options]
```

| Subcommand | Description |
|---|---|
| `list` | List the installed packs: name, version, scope (shipped, user, project), sections, licence, title |
| `search QUERY` | Print the sections best matching `QUERY` (words, symbols such as `firstprivate`, constraint ids such as `C1004`) |
| `show ID` | Print a section; `--context N` / `-C N` adds the N neighbouring sections of the same document |
| `notice PACK` | Print a pack's licence, attribution, source revision and NOTICE |
| `build SOURCES...` | Build a pack from markdown files or directories and install it |
| `add DIR` | Install an already built pack directory |
| `remove NAME` | Remove a user (or, with `--project`, project) pack; shipped packs cannot be removed |

## `search` options

| Option | Description |
|---|---|
| `--pack NAME`, `-p NAME` | Search only this pack (repeatable) |
| `-k N` | Number of results [default: 5] |
| `--json` | Print id, score, heading and text of each result as JSON |

## `build` options

| Option | Description |
|---|---|
| `--name NAME` | Pack name: lower-case letters, digits and `-` (required) |
| `--license ID` | Licence of the content (SPDX id); required unless `--private` |
| `--private` | Build without licence, for your own use only |
| `--title TEXT` | One-line description |
| `--attribution TEXT` | Author or source to credit |
| `--notice FILE` | NOTICE file to include |
| `--out DIR` | Write the pack to `DIR` instead of installing it |
| `--project` | Install in the project's packs (`.fobis/kb/`) instead of the user's |

`add` and `remove` also accept `--project`.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Success (a search with no match also exits 0) |
| `1` | Unknown pack or section, missing licence, malformed pack, nothing to remove |

## Examples

```bash
fobis kb search "MPI_Init_thread thread level" --pack mpi
fobis kb show openmp:ch07-data-environment#key-concepts -C 1
fobis kb notice openmp
fobis kb build ~/notes/ --name my-notes --private
```
