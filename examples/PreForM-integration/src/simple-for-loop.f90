program simple_for_loop
use types
type(type_1):: one
type(type_2):: two
type(type_3):: three

one%v   = 1._R8P
two%v   = 2._R4P
three%v = 3_I4P

#ifndef CPPCHECK
if (less_than(one,  2)) print*,' Ok, generic inteface correct for type_1!'
if (less_than(two,  3)) print*,' Ok, generic inteface correct for type_2!'
if (less_than(three,4)) print*,' Ok, generic inteface correct for type_3!'
#else
print*,' Ko, PFM directives face with cpp ones!'
#endif
endprogram simple_for_loop
