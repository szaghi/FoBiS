# `modernize` command

Apply the automatic lint fixes in a scratch copy and keep them only when build, tests and cases show they changed
nothing. Guide: [Verified modernisation](/advanced/modernize).

```bash
fobis modernize [options]
```

| Option | Description |
|--------|-------------|
| `--select RULES` | Fixable rules to apply (repeatable or comma-separated) [default: `MDN011,MDN021,OBS005,OBS008,OBS011`] |
| `--apply` | Write the verified fixes into the working tree (files unchanged since the analysis only) |
| `--unverified` | With `--apply`: accept a build as the only evidence (no tests, no cases) |
| `--keep` | Keep the scratch copies (path printed) |
| `--mode M` | The mode built and tested |
| `--json` | `status` (`verified`, `partial`, `failed`, `nothing`), `fixes` per rule, `checks` (`rules`, `status`, `build`, `tests`, `cases`, `evidence`), `verified`, `applied`, `notes` |
| `-f/--fobos`, `--fci` | The fobos file |

Exit code 0 when every rule is verified or nothing needs fixing; 1 when a rule is not verified; 2 for an invalid
selection or declaration.
