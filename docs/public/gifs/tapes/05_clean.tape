Output public/gifs/05_clean.gif
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

Type "# Demonstrate automatic recompilation after sources modification"
Enter
Sleep 500ms

Type "tree | slowout .15"
Enter
Sleep 4s

Type "# First build from scratch"
Sleep 500ms
Enter
Sleep 500ms

Type "fobis build | slowout .15"
Enter
Wait
Sleep 3s

Type "# Touch main.f90 — only that translation unit recompiles"
Enter
Sleep 500ms

Type "touch src/main.f90 && fobis build | slowout .15"
Enter
Wait
Sleep 3s

Type "# Full clean: removes all objects, modules, and the executable"
Enter
Sleep 500ms

Type "fobis clean | slowout .15"
Enter
Wait
Sleep 3s

Type "ls obj/ mod/ 2>&1 || echo '(empty — build artifacts removed)'"
Enter
Wait
Sleep 3s
