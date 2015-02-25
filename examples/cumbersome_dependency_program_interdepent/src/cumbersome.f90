program cumbersome
use library_1, only: print_hello_world
use library_2, only: myformat
use library_3, only: goodbye
implicit none
call print_hello_world
print myformat, "If you read me all work!"
print myformat, goodbye
stop
endprogram cumbersome
