# two more packages of the lab: strings, built with fpm (an fpm.toml, no fobos), and cmath, built with CMake through a
# recipe the index provides; solver uses all four, each built by its own build system
eval "${DOCS_FPM_SETUP:-}"
needs fpm cmake
quiet 'cp -R "$DOCS_CHAPTER/packages/." ~/src/ && ~/bin/publish strings v1.0.0 && ~/bin/publish cmath v1.0.0'
show publish-strings 'cd ~/src/strings && fobis publish --index ~/lab-index/index.toml --source file://$HOME/remotes/strings.git'
show publish-cmath 'cd ~/src/cmath && fobis publish --index ~/lab-index/index.toml --source file://$HOME/remotes/cmath.git'
quiet 'mkdir -p ~/lab-index/recipes && cp "$DOCS_CHAPTER/recipes/cmath.toml" ~/lab-index/recipes/ && sed -i "/^source = \"file:\/\/.*\/remotes\/cmath.git\"$/a recipe = \"recipes/cmath.toml\"" ~/lab-index/index.toml'
show entries 'sed -n -e "/^\[package.cmath\]/,/^\$/p" -e "/^\[package.strings\]/,/^\$/p" ~/lab-index/index.toml'
show add 'fobis add strings && fobis add cmath'
excerpt dependencies fobos '[dependencies]'
show fetch 'fobis fetch'
show prefix 'find .fobis_deps/.prefix -type f | sort'
show run 'fobis build --quiet && ./build/solver'
