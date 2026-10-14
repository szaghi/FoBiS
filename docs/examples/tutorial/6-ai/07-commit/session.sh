quiet 'git reset -q --hard'
quiet 'git apply "$DOCS_CHAPTER/midpoint.patch" && git add src/area.F90'
show diff 'git diff --cached'
show facts 'fobis commit --show-facts'
eval "${DOCS_LLM_SETUP:-}"
needs llama-server
measure commit 'fobis commit'
