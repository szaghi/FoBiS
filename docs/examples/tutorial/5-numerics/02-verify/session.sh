show update 'fobis verify --update'
show pass 'fobis verify'
quiet "sed -i 's/mod(i, 2) == 1) \* f/mod(i, 2) == 0) * f/' src/quad_rules.F90"
show diff 'git diff --stat'
show fail 'fobis verify'
quiet 'git checkout src/quad_rules.F90'
quiet 'git add verification && git commit -qm "area: reference results"'
