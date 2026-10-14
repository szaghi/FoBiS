---
title: Dependencies
---

# Dependencies

## A dependency from GitHub, pinned

```ini
[dependencies]
penf = https://github.com/szaghi/PENF :: tag=v2.0.1
```

```bash
fobis fetch          # clone into .fobis_deps/, write the lock file
fobis build          # the dependency's sources are compiled with yours
```

`tag=`, `branch=` or `rev=` pin it; `user/repo` is short for a GitHub URL. Tutorial:
[dependencies](/tutorial/first-steps/05-dependencies). Guide: [fetch](/advanced/fetch).

## Build a dependency as its own library

```ini
[dependencies]
stdlib = https://github.com/fortran-lang/stdlib :: tag=v0.5.0 :: use=fobos :: mode=gnu
```

`use=fobos` builds it with its own fobos and mode, and links your program against the library.

## Update, or refuse to change

```bash
fobis fetch --update     # move to the latest commit allowed by each pin
fobis fetch --frozen     # in CI: fail when there is no lock file
```

Guide: [the lock file](/advanced/lock-file).

## Another project on this machine

```ini
[default]
compiler = gnu
src      = ./src/
dependon = ../mylib/fobos:static
```

The other project is built in its mode `static` first (and rebuilt when it changes); its module files and library
are used. Tutorial: [a project that depends on quad](/tutorial/growing/04-dependon).

## System libraries

```ini
[default]
compiler = gnu
src      = ./src/
lib_dir  = /opt/hdf5/lib
include  = /opt/hdf5/include
ext_libs = hdf5_fortran hdf5
```

`ext_libs` are linked as `-lname`; `libs` takes full paths. Guide: [libraries](/advanced/libraries).

## Install a project from GitHub

```bash
fobis install szaghi/FLAP --tag v2.0.0 --prefix ~/.local
```

Programs go to `bin/`, libraries to `lib/`, module files to `include/`. Guide: [install](/advanced/install).

## A cluster without internet

`make standalone` (or the release asset) gives `fobis.pyz`, one file with no dependencies. Fetch on a machine with
network, copy the project with its `.fobis_deps/`, and on the cluster:

```bash
python3 fobis.pyz build --mode release
```
