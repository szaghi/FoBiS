quiet 'git reset -q --hard'
show context 'fobis ask --show-context -p src -p test "Which rule integrates cubic polynomials exactly?"'
eval "${DOCS_LLM_SETUP:-}"
needs llama-server
measure ask 'fobis ask -p src -p test "Which rule integrates cubic polynomials exactly?"'
measure beyond 'fobis ask -p src -p test "How long does simpson take on a GPU?"'
