# Intrinsic Rules

Besides user-defined rules, FoBiS.py ships four built-in *intrinsic rules* accessible via `FoBiS.py rule`:

| Rule | Description |
|---|---|
| `-get <option>` | Print the value of any fobos option |
| `-get_output_name` | Print the final output file path |
| `-ford <project-file>` | Build FORD documentation |
| `-gcov_analyzer <dir> [summary]` | Analyse gcov coverage files |

## `-get` — retrieve a fobos option

Print the value of any option defined in the selected mode:

```bash
FoBiS.py rule -get build_dir
FoBiS.py rule -mode release -get build_dir
FoBiS.py rule -f my_fobos -get obj_dir
```

This is useful in shell scripts that need to locate build artefacts:

```bash
BUILD=$(FoBiS.py rule -mode release -get build_dir)
echo "Build directory: $BUILD"
```

## `-get_output_name` — retrieve the output file path

Print the full path of the final output (executable or library):

```bash
FoBiS.py rule -get_output_name
FoBiS.py rule -mode release -get_output_name
```

The path is constructed from `build_dir` + `output` (or derived from `target` + `mklib`) as defined in the fobos mode.

## `-ford` — FORD documentation

Run the [FORD](https://github.com/Fortran-FOSS-Programmers/ford) documentation generator on a project file:

```bash
FoBiS.py rule -ford doc/ford-project.md
```

Equivalent to `ford doc/ford-project.md` but integrated into the fobos workflow. Combine with a user rule for a one-command build + document workflow:

```ini
[rule-doc]
help  = Build with FORD
quiet = True
rule  = FoBiS.py rule -ford doc/ford-project.md
```

## `-gcov_analyzer` — coverage analysis

Parse all `.gcov` files found under the current directory, generate a Markdown report for each, and optionally write a summary:

```bash
# Reports saved to ./reports/, no summary
FoBiS.py rule -gcov_analyzer reports/

# Reports + summary Markdown file
FoBiS.py rule -gcov_analyzer reports/ coverage-summary
```

The analyser generates:
- One `<filename>.gcov.md` per `.gcov` file, with line and procedure coverage tables
- An optional `<summary>.md` containing aggregate statistics and Mermaid pie charts

### Coverage workflow

```bash
# 1. Build with coverage instrumentation
FoBiS.py build -coverage

# 2. Run the program (generates .gcov data)
./myapp

# 3. Generate .gcov files
gcov -o obj/ src/*.f90

# 4. Analyse
FoBiS.py rule -gcov_analyzer reports/ summary
```
