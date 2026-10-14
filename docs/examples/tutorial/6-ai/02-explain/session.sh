quiet 'fobis build --mode release --quiet'
quiet "sed -i 's/^use quad_rules, only : R8P, trapezoid, simpson\$/use quad_rule, only : R8P, trapezoid, simpson/' src/integrate.F90"
show missing 'fobis build --mode release --quiet --explain'
quiet 'git checkout -- src/integrate.F90'
quiet "sed -i 's/abs(trapezoid(sine, 0._R8P, pi, n)/abs(trapezoid(sine, 0, pi, n)/' src/integrate.F90"
show context 'fobis build --mode release --quiet --explain-context'
eval "${DOCS_LLM_SETUP:-}"
needs llama-server
measure explain 'fobis build --mode release --quiet --explain'
