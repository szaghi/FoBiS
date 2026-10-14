show list 'fobis test --list'
show test 'fobis test'
show doctests 'fobis doctests --quiet'
needs gcovr
quiet 'fobis test --mode coverage'
show report 'fobis coverage --mode coverage --format text --exclude "test/.*" && cat coverage/coverage.txt'
