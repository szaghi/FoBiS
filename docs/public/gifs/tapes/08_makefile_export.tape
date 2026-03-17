Output public/gifs/08_makefile_export.gif
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

Type "# Export a GNU Makefile from the resolved dependency graph"
Enter
Sleep 800ms

Type "tree | slowout .15"
Enter
Sleep 4s

Type "fobis build -m Makefile | slowout .15"
Enter
Wait
Sleep 3s

Type "head -30 Makefile | slowout .15"
Enter
Wait
Sleep 5s

Type "make -f Makefile | slowout .15"
Enter
Wait
Sleep 4s

Type "fobis clean | slowout .15"
Enter
Wait
Sleep 2s
