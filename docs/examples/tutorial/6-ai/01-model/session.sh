show recommended 'fobis llm recommended'
eval "${DOCS_LLM_SETUP:-}"
needs llama-server
measure doctor 'fobis llm doctor'
measure ask 'fobis llm ask "In one sentence: what does the Fortran intrinsic merge(tsource, fsource, mask) return?"'
