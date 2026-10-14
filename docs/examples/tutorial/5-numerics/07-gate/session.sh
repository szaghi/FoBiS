quiet 'cat >> fobos <<"END"

[gate]
skip           = bench
matrix_modes   = fast
matrix_shadows = none checks
END'
excerpt section fobos '[gate]'
show gate 'fobis gate'
show update 'fobis verify fine --update'
show pass 'fobis gate'
quiet 'git add -A && git commit -qm "gate: the matrix, the reference of fine"'
