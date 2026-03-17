Output public/gifs/04_dependent_build.gif
Set FontSize 12
Set Width 800
Set Height 650
Set Theme "Dracula"
Set Framerate 24
Set WaitTimeout 60s

Sleep 1s
Type "cd $FOBIS_DEMO_DIR"
Enter
Sleep 500ms

Type "# dependon: FoBiS builds the dep library first, then links automatically"
Enter
Sleep 800ms

Type "tree | slowout .15"
Enter
Sleep 4s

Type "fobis build --mode with-dep | slowout .15"
Sleep 500ms
Enter
Wait
Sleep 5s

Type "ls -lh demo_dep dependency_lib/build/libdep.a"
Enter
Wait
Sleep 3s

Type "fobis clean | slowout .15"
Enter
Wait
Sleep 2s
