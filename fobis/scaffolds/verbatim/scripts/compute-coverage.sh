#!/usr/bin/env bash
# compute-coverage.sh — compute Fortran code coverage and emit JSON badge for VitePress
set -euo pipefail

lcov --capture --directory . --output-file coverage.info --no-external 2>/dev/null || true
TOTAL=$(lcov --summary coverage.info 2>&1 | grep -oP '[\d.]+(?=%)' | tail -1 || echo "0")
mkdir -p docs/public
INT_TOTAL="${TOTAL%.*}"
COLOR="yellow"
if [[ "$INT_TOTAL" -ge 80 ]]; then COLOR="green"; fi
cat > docs/public/coverage.json <<EOF
{"schemaVersion":1,"label":"coverage","message":"${TOTAL}%","color":"${COLOR}"}
EOF
echo "Coverage: ${TOTAL}%"
