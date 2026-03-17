Output public/gifs/03_static_library.gif
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

Type "# Build a static library instead of an executable"
Enter
Sleep 800ms

Type "tree | slowout .15"
Enter
Sleep 4s

Type "fobis build --mode static | slowout .15"
Sleep 500ms
Enter
Wait
Sleep 4s

Type "ls -lh libnested.a | slowout .15"
Enter
Wait
Sleep 3s

Type "fobis clean | slowout .15"
Enter
Wait
Sleep 2s
