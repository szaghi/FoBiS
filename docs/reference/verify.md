# `verify` command

Run cases and compare their quantities with the stored references, within each quantity's tolerance. Guide:
[Verifying results](/advanced/verify).

```bash
fobis verify [NAME...] [options]
```

| Option | Description |
|--------|-------------|
| `--update` | Accept the runs as the new references (`verification/references/<case>.json`) |
| `--repeat N` | Run each case N times; differences between the runs are reported, and `--update` refuses them |
| `--mode M` | Build with this mode instead of each case's own |
| `--json` | One JSON object: `cases`, each with status, quantity comparisons, provenance changes, run summary |
| `-f/--fobos`, `--fci` | The fobos file |

| Exit code | Meaning |
|-----------|---------|
| 0 | Every case passes (or was updated) |
| 1 | A case fails, has no reference, is non-deterministic, or did not run |
| 2 | A bad declaration, or an unknown case |
