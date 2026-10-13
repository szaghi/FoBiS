# `provenance` command

Print what a result produced now would depend on: commit and uncommitted change, dependency pins, the mode's
compiler with its version and flags, loaded environment modules, machine and GPUs. Every case run records the
same. Guide: [Cases, quantities and provenance](/advanced/cases#provenance).

```bash
fobis provenance [--mode M] [--json]
```

| Option | Description |
|--------|-------------|
| `--mode M` | The mode whose compiler and flags are recorded (default: the fobos default mode) |
| `--json` | One JSON object |
| `-f/--fobos`, `--fci` | The fobos file |
