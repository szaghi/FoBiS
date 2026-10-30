# solver uses the lab's packages: found by words, by module, by build system; added by name (a name in two indexes
# is refused), by qualified name, by module, by URL; removed
show search 'fobis search kinds'
show module 'fobis search --module vectors'
show build-system 'fobis search --build fobis'
show info 'fobis info vectors'
show ambiguous 'fobis add kinds'
show qualified 'fobis add lab:kinds'
show by-module 'fobis add --module vectors'
show by-url 'fobis add file://$HOME/remotes/timer.git'
show remove 'fobis remove timer'
excerpt dependencies fobos '[dependencies]'
show fetch 'fobis fetch'
show run 'fobis build --quiet && ./build/solver'
