# Index format

A package index is a TOML file named `index.toml`: in a git repository (at its root), served as a static file, or in
a directory. It names packages by their source URL and holds nothing else: no versions, dependencies or hashes, which
come from the sources themselves.

How to use it, with examples: [Packages and indexes](/cookbook/packages#publish-your-package-in-an-index).

```toml
schema      = 1
name        = "mylab"
description = "Fortran packages of my lab"
follows     = ["https://github.com/szaghi/fortran-index"]

[package.kinds]
source      = "https://git.example.org/mylab/kinds"
description = "Portable kind parameters"
license     = "MIT"
keywords    = ["kinds", "portability"]
provides    = ["kinds", "kinds_io"]
mirrors     = ["https://github.com/mylab/kinds"]

[package."odbc.f"]
source      = "https://github.com/davidpfister/odbc.f"
recipe      = "recipes/odbc.f.toml"
```

## Top-level keys

| Key | Value | Meaning |
|---|---|---|
| `schema` | integer, default `1` | Format version. An index with a newer schema than FoBiS reads is refused, with a request to upgrade FoBiS. |
| `name` | text | The index's name. A followed index is qualified by it (`mylab:kinds`). |
| `description` | text | What the index lists. |
| `follows` | list of URLs | Other indexes searched with this one, two levels deep by default (`--depth`). |
| `package` | tables | One `[package.NAME]` table per package. |

## Package keys

| Key | Value | Meaning |
|---|---|---|
| `source` | URL, **required** | The package's identity: a git repository, or a static directory holding a `fortran-releases.toml` manifest. `fobis add` writes it into the fobos. |
| `description` | text | Matched by `fobis search`. |
| `license` | text | An SPDX identifier, shown by `info` and the catalogue. |
| `keywords` | list of text | Matched by `fobis search`. |
| `provides` | list of module names | The modules of the package's newest version, searched by `fobis search --module` and `fobis add --module`. Stored lower-case. |
| `mirrors` | list of URLs | Other copies of the source. `fobis add` copies them into the fobos as `:: mirror=URL[,URL]`, cloned in order when the source fails. |
| `recipe` | path | A build recipe for a package without a fobos or fpm.toml, relative to the index. `fobis add` copies it into the project. |

## Rules

- **Unknown keys are refused**, `version` among them: an index never decides which version is built.
- **Names** start with a letter or a digit and hold letters, digits, `_`, `.` and `-`. They are compared without
  regard to case. A name holding a dot is written quoted: `[package."odbc.f"]`.
- **The same source in two indexes** is one package for `add`: a name both list for that source is not ambiguous.
  `search` shows it once per index.
- **Fields written by hand win:** `fobis index build` fills `description`, `license` and `provides` from each source,
  and keeps every value already present in the seeds.
- **`fobis publish --index` and `fobis index build` rewrite the whole file**, sorted by name: comments of a
  hand-written index are lost.
- **`fobis index check FILE`** validates a file without a network; `--online` also reads every source.
