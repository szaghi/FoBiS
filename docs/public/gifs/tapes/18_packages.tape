Output public/gifs/18_packages.gif
Set FontSize 13
Set Width 1120
Set Height 760
Set Theme "Dracula"
Set Framerate 24
Set WaitTimeout 120s
Set Shell bash

Sleep 500ms
Type "cd $FOBIS_DEMO_DIR"
Enter
Sleep 500ms

Type "# A package index is a file in a git repository: no server, no account"
Enter
Sleep 500ms

Type "fobis index add szaghi https://github.com/szaghi/fortran-index"
Enter
Wait
Sleep 3s

Type "fobis search json | slowout .1"
Enter
Wait
Sleep 4s

Type "fobis search --module m_cli2"
Enter
Wait
Sleep 3s

Type "fobis info json-fortran"
Enter
Wait
Sleep 5s

Type "# Add it by name: the fobos records the source URL, not the index"
Enter
Sleep 500ms

Type "fobis add json-fortran"
Enter
Wait
Sleep 2s

Type "tail -3 fobos"
Enter
Sleep 6s
