# Volatile Libraries

By default, FoBiS.py determines whether to recompile based solely on source file timestamps. External library files do not have corresponding source files, so timestamp checks cannot detect when a library has changed. *Volatile libraries* solve this problem using MD5 hashing.

## How it works

When a library is declared volatile, FoBiS.py:

1. Computes the MD5 hash of the library file and saves it alongside the build artefacts.
2. On subsequent builds, computes the hash again and compares it to the saved value.
3. If the hashes differ, a full recompile is forced — even if source timestamps are unchanged.

The hash file is saved as `.<library-filename>.md5` in the build directory.

## Full-path volatile libraries (`-vlibs`)

Use `-vlibs` for libraries referenced by their full path:

```bash
FoBiS.py build -vlibs /path/to/libmylib.a -cflags "-c -O2"
```

On the first build, `.libmylib.a.md5` is created. If `libmylib.a` is replaced (e.g. rebuilt by a CI system), the next `FoBiS.py build` detects the change and recompiles everything.

## Name-based volatile libraries (`-ext_vlibs`)

Use `-ext_vlibs` together with `-dlib` for libraries linked by name:

```bash
FoBiS.py build -ext_vlibs mylib -dlib /path/to/libs/ -cflags "-c -O2"
```

The actual library file (`libmylib.[a|so]`) must exist under the specified `lib_dir`.

## fobos options

```ini
[default]
compiler  = gnu
cflags    = -c -O2
vlibs     = ./path/to/first_volatile_lib.a
lib_dir   = ./path/to/second_lib/
ext_vlibs = second_volatile_lib
```

## Practical example: CI-generated dependency

A common scenario: your project links against a library that is rebuilt nightly by CI and dropped into a shared directory.

```bash
FoBiS.py build \
  -vlibs /shared/ci/libfoo.a \
  -i /shared/ci/mod/ \
  -cflags "-c -O2"
```

Every morning, when `libfoo.a` is refreshed, running `FoBiS.py build` automatically triggers a full recompile.

## Comparison with `-libs`

| Option | Rebuild on change? | How |
|---|---|---|
| `-libs` | No | Timestamp check only (library has no source) |
| `-vlibs` | Yes | MD5 hash comparison |
| `-ext_libs` | No | Timestamp check only |
| `-ext_vlibs` | Yes | MD5 hash comparison |
