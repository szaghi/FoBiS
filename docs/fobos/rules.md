# Rules

fobos rules let you define arbitrary shell commands to run as named tasks — documentation generation, archive creation, testing scripts, and so on. They are executed via `FoBiS.py rule -ex <name>`.

## Defining rules

Rule sections have names starting with `rule-`. Each rule can have multiple commands (prefixed with `rule`) and optional metadata:

```ini
[rule-makedoc]
help  = Build source documentation with FORD
quiet = True
rule  = ford doc/ford-project.md

[rule-maketar]
help     = Create project archive
rule_rm  = rm -f myproject.tar
rule_mk  = tar cf myproject.tar src/ fobos README.md
```

::: warning Option name uniqueness
In standard INI files, duplicate option names in the same section overwrite each other. To define multiple commands in one rule, use **different names** all starting with `rule` (e.g. `rule`, `rule_rm`, `rule_mk`, `rule1`, `rule2`, …). Only the last value of any identical name would be kept.
:::

## Executing a rule

```bash
FoBiS.py rule -ex makedoc
FoBiS.py rule -ex maketar
```

## Listing rules

```bash
FoBiS.py rule -ls
```

Output:

```
The fobos file defines the following rules:
  - "makedoc" Build source documentation with FORD
  - "maketar" Create project archive
       Command => rm -f myproject.tar
       Command => tar cf myproject.tar src/ fobos README.md
```

The `-quiet` rule option suppresses the command printing from `--list` output.

## Invalid rule error

```bash
FoBiS.py rule -ex unknown
```

```
Error: the rule "unknown" is not defined into the fobos file. Defined rules are:
  - "makedoc" Build source documentation with FORD
  - "maketar" Create project archive
```

## Using rules with fobos variables

Rules can reference `$variables` defined elsewhere in the fobos file:

```ini
[vars]
$SRC     = ./src/
$DOCDIR  = ./docs/api/

[rule-makedoc]
help  = Generate API docs
quiet = True
rule  = ford -d $SRC -o $DOCDIR doc/ford.md
```

## Complete example

```ini
[modes]
modes = gnu custom

[vars]
$SRC   = ./src/
$BUILD = ./build/

[gnu]
compiler  = gnu
cflags    = -c -O2
src       = $SRC
build_dir = $BUILD
target    = cumbersome.f90
output    = Cumbersome

[custom]
compiler  = custom
fc        = g95
modsw     = -fmod=
cflags    = -c -O2
src       = $SRC
build_dir = $BUILD
target    = cumbersome.f90
output    = Cumbersome

[rule-makedoc]
help  = Build documentation
quiet = True
rule  = echo "Building docs…"

[rule-maketar]
help    = Create project archive
rule_rm = rm -f cumbersome.tar
rule_mk = tar cf cumbersome.tar *
```
