# several programs in one build, each with its own flags; the library described for any build system;
# the compile commands for editors
show programs 'cat programs.fobos'
show build 'fobis build -f programs.fobos --quiet'
show sweep 'OMP_NUM_THREADS=2 ./build/programs/sweep | tail -n 2'
show filter 'fobis build -f programs.fobos --target-filter sweep --quiet'
excerpt static fobos '[static]'
show library 'fobis build --mode static --quiet && cat build/static/quad.pc'
quiet 'cp "$DOCS_CHAPTER/consumer/use_quad.f90" ~/use_quad.f90'
show consumer 'cd ~ && gfortran use_quad.f90 $(PKG_CONFIG_PATH=quad/build/static pkg-config --cflags --libs quad) -o use_quad && ./use_quad'
quiet 'fobis build --mode debug --compile-commands --quiet'
show database 'ls -l compile_commands.json | sed "s/.* compile_commands/compile_commands/"'
show entries 'grep -o "\"file\": \"[^\"]*/quad/\(src\|test\)/[^\"]*\"" compile_commands.json'
