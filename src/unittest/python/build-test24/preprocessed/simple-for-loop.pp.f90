# 1 "src/simple-for-loop.f90"
# 1 "<built-in>"
# 1 "<command-line>"
# 31 "<command-line>"
# 1 "/usr/include/stdc-predef.h" 1 3 4
# 32 "<command-line>" 2
# 1 "src/simple-for-loop.f90"
program simple_for_loop
use types
type(type_1):: one
type(type_2):: two
type(type_3):: three

one%v = 1._R8P
two%v = 2._R4P
three%v = 3_I4P






print*,' Ko, PFM directives face with cpp ones!'

endprogram simple_for_loop
