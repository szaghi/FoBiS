!< Composite quadrature rules on a uniform grid.
module quad_rules
!< Composite quadrature rules on a uniform grid.
use, intrinsic :: iso_fortran_env, only : R8P => real64
implicit none
private
public :: R8P, integrand, trapezoid, simpson

abstract interface
   pure function integrand(x) result(y)
   !< A function of one real variable.
   import :: R8P
   real(R8P), intent(in) :: x !< Abscissa.
   real(R8P)             :: y !< Value at x.
   endfunction integrand
endinterface

contains
   pure function trapezoid(f, a, b, n) result(s)
   !< Composite trapezoidal rule with n intervals.
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
   procedure(integrand)  :: f !< Integrand.
   real(R8P), intent(in) :: a !< Lower bound.
   real(R8P), intent(in) :: b !< Upper bound.
   integer,   intent(in) :: n !< Number of intervals, even.
   real(R8P)             :: s !< Integral estimate.
   real(R8P)             :: h !< Interval width.
   integer               :: i !< Counter.

   h = (b - a) / n
   s = f(a) + f(b)
   do i = 1, n - 1
      s = s + merge(4._R8P, 2._R8P, mod(i, 2) == 1) * f(a + i * h)
   enddo
   s = s * h / 3._R8P
   endfunction simpson
endmodule quad_rules
