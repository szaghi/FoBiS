source ./env.sh
show exec 'fobis ecosystem exec -- git log --oneline -1'
show fetch 'fobis ecosystem fetch'
show build 'fobis ecosystem exec -- fobis build --quiet'
