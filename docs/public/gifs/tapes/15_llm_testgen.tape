Output public/gifs/15_llm_testgen.gif
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
Type "# gauss_legendre has no test yet: FoBiS writes a compile-checked skeleton, the model fills it in,"
Enter
Type "# and FoBiS accepts the test only once it builds, runs and checks something"
Enter
Type "fobis testgen gauss_legendre --max 2 --apply"
Enter
Wait
Sleep 6s

Type "clear"
Enter
Type "# the first checks the model wrote: values of the 3-point rule's nodes"
Enter
Type "grep -m 2 -A 3 'if (abs' test/test_gauss_legendre.f90"
Enter
Wait
Sleep 4s

Type "clear"
Enter
Type "# the new test runs with the others"
Enter
Type "fobis test --quiet | tail -8"
Enter
Wait
Sleep 5s
