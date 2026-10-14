show skeleton 'fobis testgen gauss_legendre --skeleton'
eval "${DOCS_LLM_SETUP:-}"
needs llama-server
measure testgen 'fobis testgen gauss_legendre --max 2'
