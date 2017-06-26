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


if (less_than(one, 2)) print*,' Ok, generic inteface correct for type_1!'
if (less_than(two, 3)) print*,' Ok, generic inteface correct for type_2!'
if (less_than(three,4)) print*,' Ok, generic inteface correct for type_3!'



endprogram simple_for_loop
