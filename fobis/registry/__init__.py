"""
Decentralised package indexes (issue #209).

An index is a small TOML file naming packages by their source URL: it holds no versions, dependencies or hashes,
which come from the source itself. Several indexes live side by side, and none is read at build or fetch time:
``fobis add`` resolves a name once and writes the URL into the fobos.

Modules: `index` (schema, providers, cache, graph walk), `sources` (source providers and the probe chain),
`fobosedit` (line-based edits of a fobos ``[dependencies]`` section).
"""
