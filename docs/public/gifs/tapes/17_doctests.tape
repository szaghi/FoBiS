Output public/gifs/17_doctests.gif
Set FontSize 13
Set Width 1000
Set Height 650
Set Theme "Dracula"
Set Framerate 24
Set WaitTimeout 120s
Set Shell bash

Sleep 500ms
Type "cd $FOBIS_DEMO_DIR"
Enter
Sleep 500ms

Type "# Doctests: the example in a procedure's documentation, run and checked"
Enter
Sleep 500ms

Type "sed -n '/pure function trapezoid/,/<<</p' src/quad_rules.F90 | slowout .15"
Enter
Sleep 5s

Type "fobis doctests --quiet"
Enter
Wait
Sleep 4s

Type "# The documentation drifts from the code: the doctest says so"
Enter
Sleep 500ms

Type "sed -i 's/=> 1.99960/=> 2.00000/' src/quad_rules.F90"
Enter
Sleep 500ms

Type "fobis doctests --quiet"
Enter
Wait
Sleep 6s
