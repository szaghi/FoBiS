# `fpm` command

Translate between an `fpm.toml` and a fobos. Guide: [fpm interoperability](/advanced/fpm).

```bash
fobis fpm import [options]
fobis fpm export [options]
```

| `import` option | Description |
|--------|-------------|
| `--fpm FILE` | The manifest to read [default: `fpm.toml`] |
| `-o/--output FILE` | The fobos to write [default: `fobos`] |
| `--compiler NAME` | Compiler of the generated modes [default: `gnu`] |

| `export` option | Description |
|--------|-------------|
| `-o/--output FILE` | The manifest to write [default: `fpm.toml`] |
| `--mode M` | The mode whose sources, MPI/OpenMP and macros are exported [default: the first] |
| `-f/--fobos`, `--fci` | The fobos file |

Both: `--force` (overwrite), `--print` (print, write nothing), `--json` (`written`, `text`, `notes`). Exit code 0;
2 when the output exists without `--force`, the input is missing or unreadable.
