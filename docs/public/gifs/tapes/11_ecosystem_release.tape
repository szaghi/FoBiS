Output public/gifs/11_ecosystem_release.gif
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
Type "# What needs a release? Releasable commits, bump from Conventional Commits"
Enter
Sleep 800ms

Type "fobis ecosystem release --dry-run"
Enter
Wait
Sleep 4s

Type "clear"
Enter
Type "# The release train: confirm the plan, then each release.sh asks its own question"
Enter
Sleep 800ms

Type "fobis ecosystem release --no-fetch"
Enter
Wait /Release 1 project/
Sleep 1.5s
Type "y"
Sleep 400ms
Enter
Wait /Proceed\?/
Sleep 1.5s
Type "y"
Sleep 400ms
Enter
Wait
Sleep 3s

Type "clear"
Enter
Type "fobis ecosystem dashboard --no-ci --no-fetch"
Enter
Wait
Sleep 5s
