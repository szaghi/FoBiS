Output public/gifs/02_fobos_build.gif
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

Type "# Build a project using fobos file"
Enter
Sleep 800ms

Type "tree | slowout .15"
Enter
Sleep 4s

Type "cat fobos | slowout 0.15"
Enter
Sleep 4s

Type "fobis build | slowout 0.15"
Sleep 500ms
Enter
Wait
Sleep 4s

Type "# Build in release mode with -O3:"
Enter
Sleep 500ms

Type "fobis build --mode release | slowout 0.15"
Sleep 500ms
Enter
Wait
Sleep 4s

Type "ls -lh | slowout .15"
Enter
Wait
Sleep 5s

Type "fobis clean"
Enter
Wait
Sleep 2s
