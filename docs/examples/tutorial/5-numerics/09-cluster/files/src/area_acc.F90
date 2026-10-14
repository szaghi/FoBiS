!< The integral of sin(x) over [0, pi], exact value 2, by the trapezoidal rule on a GPU (OpenACC).
program area_acc
!< The integral of sin(x) over [0, pi], exact value 2, by the trapezoidal rule on a GPU (OpenACC).
use, intrinsic :: iso_fortran_env, only : R8P => real64
implicit none
integer,   parameter  :: n = 100000000        !< Number of intervals.
real(R8P), parameter  :: pi = acos(-1._R8P)   !< Pi.
real(R8P), allocatable :: y(:)                !< Samples of sin(x) at the n + 1 nodes.
real(R8P)             :: h                    !< Interval width.
real(R8P)             :: s                    !< Integral estimate.
integer               :: i                    !< Counter.

allocate(y(0:n))
h = pi / n
!$acc data create(y)
!$acc parallel loop
do i = 0, n
   y(i) = sin(i * h)
enddo
s = 0._R8P
!$acc parallel loop reduction(+:s)
do i = 1, n - 1
   s = s + y(i)
enddo
!$acc update self(y)
!$acc end data
s = (s + 0.5_R8P * (y(0) + y(n))) * h
print '(A, I0)', 'n = ', n
print '(A, ES24.17)', 'trapezoid = ', s
endprogram area_acc
