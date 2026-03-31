#!/usr/bin/env bash
# run_tests.sh — build and run the project test suite
set -euo pipefail

FoBiS.py build -f fobos -mode tests 2>&1
if [[ -x ./test_suite ]]; then
  ./test_suite
fi
