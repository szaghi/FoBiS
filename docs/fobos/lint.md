# `[lint]` section

The optional `[lint]` section fixes how [`fobis lint`](/ai/lint) runs for the project, so that every
developer and the CI apply the same rules.

```ini
[lint]
; rule ids or prefixes; default: the rules enabled by default
select   = COR, OBS
; rule ids or prefixes to skip
ignore   = COR040, OBS011
baseline = .fobis-lint-baseline.json
```

| Key | Value | Default |
|-----|-------|---------|
| `select` | Rule ids or prefixes, comma- or space-separated; `ALL` for every rule. An explicit selection also enables opt-in rules. | the rules enabled by default |
| `ignore` | Rule ids or prefixes to skip. | none |
| `baseline` | Baseline file: findings recorded there are not reported (see [the baseline](/ai/lint#adopting-the-linter-on-an-existing-code-the-baseline)). | `.fobis-lint-baseline.json`, when it exists |

Command-line options take precedence: `--select` replaces `select`, `--ignore` adds to `ignore`,
`--baseline` replaces `baseline`.

The sources, the excluded paths and the preprocessor defines come from the selected mode
(`fobis lint --mode NAME`), exactly as for `fobis build`.
