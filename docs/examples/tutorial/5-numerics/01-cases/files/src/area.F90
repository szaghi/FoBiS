!< The integral of sin(x) over [0, pi], exact value 2, with n intervals (the first argument, default 16).
program area
!< The integral of sin(x) over [0, pi], exact value 2, with n intervals (the first argument, default 16).
use quad_rules, only : R8P, trapezoid, simpson
use integrands, only : sine
implicit none
real(R8P), parameter :: pi = acos(-1._R8P) !< Pi.
character(len=32)    :: arg                !< The first argument.
integer              :: n                  !< Number of intervals.

n = 16
if (command_argument_count() > 0) then
   call get_command_argument(1, arg)
   read(arg, *) n
endif
print '(A, I0)', 'n = ', n
print '(A, ES24.17)', 'trapezoid = ', trapezoid(sine, 0._R8P, pi, n)
print '(A, ES24.17)', 'simpson = ', simpson(sine, 0._R8P, pi, n)
endprogram area
