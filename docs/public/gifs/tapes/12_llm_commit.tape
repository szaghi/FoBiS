Output public/gifs/12_llm_commit.gif
Set FontSize 13
Set Width 1100
Set Height 620
Set Theme "Dracula"
Set Framerate 24
Set WaitTimeout 180s
Set Shell bash

Hide
Type "cd $FOBIS_DEMO_DIR && git init -q && git add -A && git -c user.name=demo -c user.email=d@d commit -qm 'feat: demo project' && sed -i 's/character(len=20), parameter/character(len=*), parameter/' src/nested-1/nested-2/second_dep.inc && git add -A && clear"
Enter
Show

Sleep 1s
Type "# FoBiS runs the model itself: llama.cpp + an open model, no service to install"
Enter
Sleep 800ms
Type "fobis llm doctor"
Enter
Wait
Sleep 3s

Type "clear"
Enter
Type "git diff --cached --stat"
Enter
Sleep 1500ms
Type "fobis commit"
Enter
Wait
Sleep 6s
