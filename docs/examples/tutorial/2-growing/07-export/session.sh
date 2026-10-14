show fpm 'fobis fpm export --mode release --print'
show makefile 'fobis build --mode release --makefile Makefile --quiet && sed -n "1,30p" Makefile'
show make 'rm -rf build/release && make && ./build/release/integrate | tail -n 1'
