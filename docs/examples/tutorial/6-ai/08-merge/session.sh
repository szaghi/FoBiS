quiet 'git reset -q --hard && fobis test --quiet'  # the modules built: merge-assist compiles its proposals
quiet 'git checkout -qb midpoint && git apply "$DOCS_CHAPTER/topic.patch" && git commit -qam "test: midpoint is exact on a line too"'
quiet 'git checkout -q master && git apply "$DOCS_CHAPTER/master.patch" && git commit -qam "test: a tolerance of a few ulps, for -O3 builds"'
show merge 'git merge midpoint'
show conflict 'git diff'
show deterministic 'fobis merge-assist --no-model'
eval "${DOCS_LLM_SETUP:-}"
needs llama-server
measure merge 'fobis merge-assist'
