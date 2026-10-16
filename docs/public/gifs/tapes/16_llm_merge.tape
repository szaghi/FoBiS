Output public/gifs/16_llm_merge.gif
Set FontSize 13
Set Width 1180
Set Height 700
Set Theme "Dracula"
Set Framerate 24
Set TypingSpeed 40ms
Set WaitTimeout 300s
Set Shell bash

Hide
Type "cd $FOBIS_DEMO_DIR && clear"
Enter
Wait
Show
Type "# quad, the tutorial's project. The model, coder-7b, runs on an NVIDIA A30 of a cluster node, through ssh"
Enter
Type "# two branches changed the same tolerance of a test"
Enter
Type "git merge midpoint"
Enter
Wait
Sleep 2500ms

Type "clear"
Enter
Type "# the rules of merge-assist (use lists, appended lines, dependency pins) find no safe answer: no model"
Enter
Type "fobis merge-assist --no-model"
Enter
Wait
Sleep 4s

Type "clear"
Enter
Type "# the model proposes a resolution; FoBiS compiles every proposal before showing it"
Enter
Type "fobis merge-assist"
Enter
Wait
Sleep 9s
