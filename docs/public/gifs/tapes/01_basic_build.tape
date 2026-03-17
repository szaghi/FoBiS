Output public/gifs/01_basic_build.gif
Set FontSize 12
Set Width 800
Set Height 650
Set Theme "Dracula"
Set Framerate 24
Set WaitTimeout 60s

Sleep 500ms
Type "cd $FOBIS_DEMO_DIR && rm -f fobos"
Enter
Sleep 500ms

Type "# Zero-config: FoBiS resolves nested module dependencies automatically"
Enter
Sleep 500ms

Type "tree | slowout .15"
Enter
Sleep 5s

Type "fobis build --colors | slowout .15"
Sleep 500ms
Enter
Wait
Sleep 2s

Type "ls -lh | slowout .15"
Enter
Wait
Sleep 5s

Type "fobis clean --colors | slowout .15"
Enter
Wait
Sleep 2s
