# GNU Makefile Export

FoBiS.py can export a valid GNU Makefile instead of building the project. This is useful when you need to hand off a build system to users who don't have FoBiS.py installed, or when integrating with tools that expect a Makefile.

## Generating a Makefile

Use the `-m`/`--makefile` flag with the `build` command:

```bash
FoBiS.py build -m makefile
```

The project is **not** actually compiled — only the Makefile is written. All the usual build options apply and are encoded into the generated Makefile.

## Using fobos as a translator

Combine `-m` with a fobos file to translate from fobos syntax to GNU Make syntax:

```bash
FoBiS.py build -m makefile -f project.fobos -mode release
```

This is a convenient workflow for distributing a project: maintain the build configuration in a concise fobos file and generate the Makefile on demand.

## Auxiliary Makefile rules

The generated Makefile includes auxiliary targets beyond the default build rule:

- `clean` — remove objects, modules, and built targets
- `mkdir` (or similar) — create the build directory structure

## Automating with a fobos rule

Add a rule to your fobos file to generate the Makefile in one command:

```ini
[rule-genmakefile]
help = Generate a GNU Makefile from fobos settings
rule = FoBiS.py build -m makefile
```

Then:

```bash
FoBiS.py rule -ex genmakefile
```

## Example

```bash
# Inspect build settings in fobos, generate a Makefile
FoBiS.py build -m Makefile -f project.fobos -mode release

# Hand the Makefile to a user without FoBiS.py
make
make clean
```

## Notes

- The Makefile uses the same compiler, flags, source paths, and include directories that FoBiS.py would use for the build.
- Dependency ordering between object files is encoded explicitly in the Makefile, so `make` does not need to resolve them.
- The Makefile is regenerated each time the command is run; it does not update incrementally.
