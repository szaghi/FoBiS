source ./env.sh
needs git-cliff
show plan 'fobis ecosystem release --dry-run --no-wait'
show release 'fobis ecosystem release --yes --no-wait'
show after 'fobis ecosystem dashboard --no-ci'
