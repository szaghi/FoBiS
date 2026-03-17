Output public/gifs/07_fetch.gif
Set FontSize 12
Set Width 800
Set Height 650
Set Theme "Dracula"
Set Framerate 24
Set WaitTimeout 120s

Sleep 1s
Type "cd $FOBIS_DEMO_DIR"
Enter
Sleep 500ms

Type "# Fetch deps declared in the [dependencies] section"
Enter
Sleep 500ms

Type "tree | slowout .15"
Enter
Sleep 4s

Type "cat fobos | slowout .15"
Enter
Sleep 4s

Type "fobis fetch | slowout .15"
Sleep 500ms
Enter
Hide
Wait
Show
Sleep 4s

Type "cat .fobis_deps/.deps_config.ini | slowout .15"
Enter
Wait
Sleep 3s

Type "# Build — dep sources are auto-loaded from .deps_config.ini"
Enter
Sleep 500ms

Type "fobis build | slowout .15"
Enter
Wait
Sleep 4s
