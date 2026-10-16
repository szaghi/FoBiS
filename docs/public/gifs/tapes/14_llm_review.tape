Output public/gifs/14_llm_review.gif
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
Type "# a change to review: the sweep of the integrals is now parallel, with OpenMP"
Enter
Type "git --no-pager diff"
Enter
Wait
Sleep 4s

Type "clear"
Enter
Type "# the review lints the project and keeps the findings on the changed lines: no model"
Enter
Type "fobis review"
Enter
Wait
Sleep 3500ms

Type "clear"
Enter
Type "# --deep adds a risk summary: the model reads the diff, the regions and the rules, and cites them"
Enter
Type "fobis review --deep"
Enter
Wait
Sleep 8s
