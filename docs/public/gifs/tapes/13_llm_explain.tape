Output public/gifs/13_llm_explain.gif
Set FontSize 13
Set Width 1180
Set Height 700
Set Theme "Dracula"
Set Framerate 24
Set TypingSpeed 40ms
Set WaitTimeout 400s
Set Shell bash

# the model is loaded once, off camera; make_gifs.sh stops it after the tape
Hide
Type "cd $FOBIS_DEMO_DIR && nice -n 19 fobis llm serve start > /dev/null 2>&1; clear"
Enter
Wait
Show

Type "# quad, quadrature rules in Fortran. The model, coder-7b, runs on this machine, on 6 CPU cores, no GPU:"
Enter
Type "fobis llm serve status"
Enter
Wait
Sleep 2500ms

Type "clear"
Enter
Type "# an edit with a mistake: an integer where trapezoid wants a real(R8P)"
Enter
Type "sed -i 's/trapezoid(sine, 0._R8P, pi, n)/trapezoid(sine, 0, pi, n)/' src/integrate.F90"
Enter
Sleep 600ms
Type "# FoBiS reads the error, the code and the interfaces; the model explains, citing them"
Enter
Type "# (each answer takes about 45 s on the CPU: the waits are cut from this recording)"
Enter
Sleep 800ms
Type "fobis build --quiet --explain"
Enter
Sleep 3s
Hide
Wait
Show
Sleep 10s

Type "clear"
Enter
Type "# the human applies the fix: FoBiS recompiles what changed, and the program runs"
Enter
Type "sed -i 's/trapezoid(sine, 0, pi, n)/trapezoid(sine, 0._R8P, pi, n)/' src/integrate.F90"
Enter
Type "fobis build --quiet && ./integrate | head -4"
Enter
Wait
Sleep 3500ms

Type "clear"
Enter
Type "# questions are answered from the project's sources, with the source of each claim"
Enter
Type 'fobis ask -p src "What does simpson require of the number of intervals?"'
Enter
Sleep 2s
Hide
Wait
Show
Sleep 8s
