# `merge-assist` command

Propose resolutions for the conflicts of a merge, rebase or cherry-pick, checked by the compiler. The git state is
never changed.

```bash
fobis merge-assist [PATHS...] [options]
```

`PATHS` restricts the work to these conflicted files (default: every conflicted file). Guide:
[Resolving merge conflicts](/ai/merge-assist).

## Options

| Option | Description |
|--------|-------------|
| `--apply` | Ask hunk by hunk (`a`ccept, `o`urs, `t`heirs, `b`oth, `e`dit in `$EDITOR`, `s`kip, `q`uit) and write the accepted resolutions to the working tree |
| `--yes` | With `--apply`, no questions: accept the high-confidence rules and the model proposals that compile |
| `--no-model` | Deterministic rules only |
| `--context` | Print what the model would receive for each conflict the rules do not settle, run no model |
| `--format text\|json` | `json`: the report as one JSON object on stdout (conflicts, resolutions, compile checks); asks nothing, so `--apply` needs `--yes` |
| `--mode`, `-f/--fobos`, `--fci` | The fobos mode whose compiler, flags and module directory verify the proposals |

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | Done (also when conflicts remain: the report says which) |
| 1 | Not a git repository, or `--apply` without a terminal and without `--yes` |
