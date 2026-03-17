Output public/gifs/06_install.gif
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

Type "# Build with artifact tracking, then install to a prefix"
Enter
Sleep 800ms

Type "tree | slowout .15"
Enter
Sleep 4s

Type "fobis build --tb | slowout .15 && fobis install --prefix ./local | slowout .15"
Enter
Wait
Sleep 4s

Type "find ./local -type f | slowout .15"
Enter
Wait
Sleep 3s

Type "fobis clean | slowout .15"
Enter
Wait
Sleep 2s
