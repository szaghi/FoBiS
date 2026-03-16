# `rule` command

Execute user-defined rules from a fobos file, or run one of the built-in intrinsic rules.

```bash
fobis rule [options]
```

## Rule options

| Option | Description |
|---|---|
| `--ex RULE`, `--execute RULE` | Execute the named rule defined in the fobos file |
| `--ls`, `--list` | List all rules defined in the fobos file |

## Intrinsic rule options

| Option | Description |
|---|---|
| `--get OPTION` | Print the value of any fobos option |
| `--get-output-name` | Print the final output file path |
| `--ford project-file.md` | Build FORD documentation |
| `--gcov-analyzer DIR [SUMMARY]` | Analyse gcov coverage files, write reports to `DIR` |
| `--is-ascii-kind-supported` | Check whether the compiler supports ASCII kind |
| `--is-ucs4-kind-supported` | Check whether the compiler supports UCS4 kind |
| `--is-float128-kind-supported` | Check whether the compiler supports float128 kind |

## fobos options

| Option | Description |
|---|---|
| `-f`, `--fobos` | Specify a fobos file with a different name or path |
| `--fci`, `--fobos-case-insensitive` | Case-insensitive fobos option parsing |
| `--mode` | Select a fobos mode — tab-completable from the active fobos file |
| `--lmodes` | List available modes and exit |
| `--print-fobos-template` | Print a fobos template |

## Fancy options

| Option | Description |
|---|---|
| `--colors` | Coloured terminal output |
| `-l`, `--log` | Write a log file |
| `-q`, `--quiet` | Less verbose output |
| `--verbose` | Maximum verbosity |

## Examples

### User-defined rules

```bash
# List all rules in the fobos file
fobis rule --ls

# Execute a rule named "makedoc"
fobis rule --ex makedoc

# Execute a rule in a specific fobos mode
fobis rule -f project.fobos --mode release --ex package
```

### Intrinsic rules

```bash
# Print the build_dir value for a given mode
fobis rule --mode release --get build_dir

# Print the full output path (executable or library)
fobis rule --mode release --get-output-name

# Build FORD documentation
fobis rule --ford doc/ford-project.md

# Analyse coverage files and write a summary
fobis rule --gcov-analyzer reports/ coverage-summary
```

### Shell script integration

```bash
# Locate built artefacts in a script
EXE=$(fobis rule --mode release --get-output-name)
strip "$EXE"
```

## Defining rules in fobos

```ini
[rule-makedoc]
help  = Build source documentation
quiet = True
rule  = ford doc/ford.md

[rule-package]
help    = Create release archive
rule_rm = rm -f myproject.tar.gz
rule_mk = tar czf myproject.tar.gz src/ fobos README.md
```

See the [Rules](/fobos/rules) and [Intrinsic Rules](/fobos/intrinsic-rules) pages for full details.
