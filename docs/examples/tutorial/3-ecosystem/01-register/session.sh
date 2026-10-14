quiet 'bash "$DOCS_CHAPTER/../../../../demo/ecosystem-demo/setup.sh" .'
source ./env.sh
quiet 'printf "[ecosystem]\nroot = %s\n" "$PWD" > .config/fobis/config.ini'
show ls 'ls'
show deps 'cat app/fobos | sed -n "/dependencies/,/^$/p"'
show discover 'fobis ecosystem discover'
show add 'fobis ecosystem add core mathx app'
show graph 'fobis ecosystem graph'
