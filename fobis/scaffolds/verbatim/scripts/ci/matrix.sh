#!/usr/bin/env bash
# The project's pipeline on one toolchain, run by .github/workflows/matrix.yml on each toolchain of the fobos
# [scaffold] matrix, with the fortran-toolchains environment contract: FC, CC, CXX, TOOLCHAIN, TOOLCHAIN_OS and
# TOOLCHAIN_FAMILY (gnu, nvf, intel). Created once by fobis scaffold, then the project's: edit it freely. The same
# script runs locally, in `docker run <image>` and in CI.
set -euo pipefail
echo "toolchain: $TOOLCHAIN ($TOOLCHAIN_OS, $TOOLCHAIN_FAMILY), FC=$FC"
fobis build --mode "tests-$TOOLCHAIN_FAMILY"
bash scripts/run_tests.sh
