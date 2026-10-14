!< Composite quadrature rules on a uniform grid.
module quad_rules
!< Composite quadrature rules on a uniform grid.
use, intrinsic :: iso_fortran_env, only : R8P => real64
implicit none
private
public :: R8P, integrand, midpoint, trapezoid, simpson

abstract interface
   pure function integrand(x) result(y)
   !< A function of one real variable.
   import :: R8P
   implicit none
   real(R8P), intent(in) :: x !< Abscissa.
   real(R8P)             :: y !< Value at x.
   endfunction integrand
endinterface

contains
   pure function midpoint(f, a, b, n) result(s)
   !< Composite midpoint rule with n intervals.
   procedure(integrand)  :: f !< Integrand.
   real(R8P), intent(in) :: a !< Lower bound.
   real(R8P), intent(in) :: b !< Upper bound.
   integer,   intent(in) :: n !< Number of intervals.
   real(R8P)             :: s !< Integral estimate.
   real(R8P)             :: h !< Interval width.
   integer               :: i !< Counter.

   h = (b - a) / n
   s = 0._R8P
   do i = 1, n
      s = s + f(a + (i - 0.5_R8P) * h)
   enddo
   s = s * h
   endfunction midpoint

   pure function trapezoid(f, a, b, n) result(s)
   !< Composite trapezoidal rule with n intervals.
   !<```fortran
   !< use integrands, only : sine
   !< print '(F8.5)', trapezoid(sine, 0._R8P, acos(-1._R8P), 64)
   !<```
   !=> 1.99960 <<<
   procedure(integrand)  :: f !< Integrand.
   real(R8P), intent(in) :: a !< Lower bound.
   real(R8P), intent(in) :: b !< Upper bound.
   integer,   intent(in) :: n !< Number of intervals.
   real(R8P)             :: s !< Integral estimate.
   real(R8P)             :: h !< Interval width.
   integer               :: i !< Counter.

   h = (b - a) / n
   s = 0.5_R8P * (f(a) + f(b))
   do i = 1, n - 1
      s = s + f(a + i * h)
   enddo
   s = s * h
   endfunction trapezoid

   pure function simpson(f, a, b, n) result(s)
   !< Composite Simpson rule with n intervals (n even).
   !<```fortran
   !< use integrands, only : sine
   !< print '(F8.5)', simpson(sine, 0._R8P, acos(-1._R8P), 64)
   !<```
   !=> 2.00000 <<<
   procedure(integrand)  :: f !< Integrand.
   real(R8P), intent(in) :: a !< Lower bound.
   real(R8P), intent(in) :: b !< Upper bound.
   integer,   intent(in) :: n !< Number of intervals, even.
   real(R8P)             :: s !< Integral estimate.
   real(R8P)             :: h !< Interval width.
   real(R8P)             :: odd  !< Sum at the odd nodes.
   real(R8P)             :: even !< Sum at the even inner nodes.
   integer               :: i    !< Counter.

#ifdef QUAD_CHECKS
   if (mod(n, 2) /= 0) error stop 'simpson: the number of intervals must be even'
#endif
   h = (b - a) / n
   odd = 0._R8P
   do i = 1, n - 1, 2
      odd = odd + f(a + i * h)
   enddo
   even = 0._R8P
   do i = 2, n - 2, 2
      even = even + f(a + i * h)
   enddo
   s = (f(a) + f(b) + 4._R8P * odd + 2._R8P * even) * h / 3._R8P
   endfunction simpson
endmodule quad_rules
