Output public/gifs/10_ecosystem_check.gif
Set FontSize 13
Set Width 1100
Set Height 620
Set Theme "Dracula"
Set Framerate 24
Set WaitTimeout 180s
Set Shell bash

Hide
Type "source $FOBIS_DEMO_DIR/env.sh && cd $FOBIS_DEMO_DIR && clear"
Enter
Show

Sleep 1s
Type "# Rename twice() to double() in core, uncommitted: who breaks downstream?"
Enter
Sleep 800ms

Type "sed -i 's/twice/double/g' core/src/*.f90"
Enter
Sleep 1s

Type "fobis ecosystem check core --fail-fast"
Enter
Wait
Sleep 5s

Type "clear"
Enter
Type "# Revert, and check again: every dependent is rebuilt from scratch and tested"
Enter
Sleep 800ms

Type "git -C core checkout -- src && fobis ecosystem check core"
Enter
Wait
Sleep 5s
