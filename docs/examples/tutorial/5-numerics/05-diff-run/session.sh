show test 'fobis test --quiet'
show verify 'fobis verify'
show diffrun 'fobis diff-run HEAD'
show assess 'fobis diff-run HEAD --assess'
quiet "sed -i 's/^quantities  = stdout\$/quantities  = stdout\ntolerance   = *: ulp 4/' fobos"
excerpt case fobos '[case:area]'
show equivalent 'fobis diff-run HEAD'
show verified 'fobis verify'
quiet 'git add -A && git commit -qm "simpson: the odd and the even nodes summed apart"'
