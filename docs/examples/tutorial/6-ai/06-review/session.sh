quiet 'cp "$DOCS_CHAPTER/racy/sweep.F90" src/sweep.F90'
show review 'fobis review'
show context 'fobis review --deep-context'
eval "${DOCS_LLM_SETUP:-}"
needs llama-server
measure deep 'fobis review --deep'
