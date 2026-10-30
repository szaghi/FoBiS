---
title: 4. Install for your compiler
---

# 4. Install for your compiler

Not every user of `vectors` builds with FoBiS: a colleague compiles by hand, another project uses CMake. They need
`vectors` installed, as a library and its module files. A module file works only with the compiler that wrote it, so
there is no prebuilt package to download: `fobis pkg install` builds the package from its source with your compiler.

<<< @/examples/output/7-packages/04/install.measured.txt{console}

The package is filed under a toolchain key: the compiler family, its version, and a digest of the compiler's path,
MPI and flags. Installing with another compiler, or other flags, gives another key, and both stay installed.
`vectors` brings `kinds` along, because its library contains what it uses.

<<< @/examples/output/7-packages/04/list.measured.txt{console}

## Use it from any build system

Each library gets a pkg-config file. `fobis pkg path --pkgconfig` gives its directory:

<<< @/examples/output/7-packages/04/path.measured.txt{console}

<<< @/examples/tutorial/7-packages/04-install/consumer/length.f90{fortran}

<<< @/examples/output/7-packages/04/consumer.measured.txt{console}

CMake reads the same file with `pkg_check_modules`, make with `pkg-config --cflags --libs vectors`.

## Upgrade and uninstall

The lab publishes `vectors` 0.2.1, a patch release. `fobis pkg upgrade` installs the newest version the original
request allows, for the same toolchain, and removes the old one. The install named no `--version`, so any newer
version qualifies; `pkg install lab:vectors --version "^0.2"` would have kept the upgrades within 0.x from 0.2:

<<< @/examples/output/7-packages/04/upgrade.measured.txt{console}

`uninstall` removes exactly the files and links the install wrote, recorded in the store:

<<< @/examples/output/7-packages/04/uninstall.measured.txt{console}

<<< @/examples/output/7-packages/04/empty.txt{console}

*The outputs above depend on the machine: the key names the compiler and its path.*

::: tip What you learned
`fobis pkg install`, toolchain keys, `pkg list`, `pkg path --pkgconfig`, linking from another build system,
`pkg upgrade`, `pkg uninstall`. Reference: [`pkg`](/reference/pkg),
[install a package for your compiler](/cookbook/packages#install-a-package-for-your-compiler).
:::

Next: [trust without a central server](./05-trust).
