Output public/gifs/09_ecosystem_dashboard.gif
Set FontSize 13
Set Width 1100
Set Height 560
Set Theme "Dracula"
Set Framerate 24
Set WaitTimeout 120s
Set Shell bash

Hide
Type "source $FOBIS_DEMO_DIR/env.sh && cd $FOBIS_DEMO_DIR && clear"
Enter
Show

Sleep 1s
Type "# Three interconnected Fortran projects: core <- mathx <- app"
Enter
Sleep 800ms

Type "fobis ecosystem graph"
Enter
Wait
Sleep 3s

Type "# Their state at a glance: git, releases, CI, scaffold drift, dependency pins"
Enter
Sleep 800ms

Type "fobis ecosystem dashboard --no-ci"
Enter
Wait
Sleep 6s
