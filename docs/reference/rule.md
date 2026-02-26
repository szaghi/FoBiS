# `rule` command

Execute user-defined rules from a fobos file, or run one of the built-in intrinsic rules.

```bash
FoBiS.py rule [options]
```

## Rule options

| Option | Description |
|---|---|
| `-ex RULE`, `--execute RULE` | Execute the named rule defined in the fobos file |
| `-ls`, `--list` | List all rules defined in the fobos file |

## Intrinsic rule options

| Option | Description |
|---|---|
| `-get OPTION` | Print the value of any fobos option |
| `-get_output_name` | Print the final output file path |
| `-ford project-file.md` | Build FORD documentation |
| `-gcov_analyzer DIR [SUMMARY]` | Analyse gcov coverage files, write reports to `DIR` |
| `-is_ascii_kind_supported` | Check whether the compiler supports ASCII kind |
| `-is_ucs4_kind_supported` | Check whether the compiler supports UCS4 kind |
| `-is_float128_kind_supported` | Check whether the compiler supports float128 kind |

## fobos options

| Option | Description |
|---|---|
| `-f`, `--fobos` | Specify a fobos file with a different name or path |
| `-fci`, `--fobos_case_insensitive` | Case-insensitive fobos option parsing |
| `-mode` | Select a fobos mode |
| `-lmodes` | List available modes and exit |
| `--print_fobos_template` | Print a fobos template |

## Fancy options

| Option | Description |
|---|---|
| `-colors` | Coloured terminal output |
| `-l`, `--log` | Write a log file |
| `-q`, `--quiet` | Less verbose output |
| `-verbose` | Maximum verbosity |

## Examples

### User-defined rules

```bash
# List all rules in the fobos file
FoBiS.py rule -ls

# Execute a rule named "makedoc"
FoBiS.py rule -ex makedoc

# Execute a rule in a specific fobos mode
FoBiS.py rule -f project.fobos -mode release -ex package
```

### Intrinsic rules

```bash
# Print the build_dir value for a given mode
FoBiS.py rule -mode release -get build_dir

# Print the full output path (executable or library)
FoBiS.py rule -mode release -get_output_name

# Build FORD documentation
FoBiS.py rule -ford doc/ford-project.md

# Analyse coverage files and write a summary
FoBiS.py rule -gcov_analyzer reports/ coverage-summary
```

### Shell script integration

```bash
# Use -get to locate build artefacts in a script
EXE=$(FoBiS.py rule -mode release -get_output_name)
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
