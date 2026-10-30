# vectors installed for this compiler, outside any project; used through pkg-config; upgraded within its range when
# a patch release appears; uninstalled
measure install 'fobis pkg install lab:vectors'
measure list 'fobis pkg list'
measure path 'fobis pkg path vectors --pkgconfig'
quiet 'cp "$DOCS_CHAPTER/consumer/length.f90" ~/length.f90'
measure consumer 'cd ~ && export PKG_CONFIG_PATH=$(fobis pkg path vectors --pkgconfig) && gfortran length.f90 $(pkg-config --cflags --libs vectors) -o length && ./length'
quiet 'cd ~/src/vectors && sed -i "s/Euclidean norm./Euclidean norm (2-norm)./" src/vectors.f90 && ~/bin/publish vectors v0.2.1'
measure upgrade 'fobis pkg upgrade vectors'
measure uninstall 'fobis pkg uninstall vectors'
show empty 'fobis pkg list'
