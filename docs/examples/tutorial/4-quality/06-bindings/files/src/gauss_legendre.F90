!< Gauss-Legendre quadrature: nodes and weights on [-1, 1].
module gauss_legendre
!< Gauss-Legendre quadrature: nodes and weights on [-1, 1].
use quad_rules, only : R8P
implicit none
private
public :: gauss_nodes

contains
   pure subroutine gauss_nodes(n, x, w)
   !< Nodes and weights of the n-point rule: the roots of the Legendre polynomial P_n, by Newton's method.
   integer,   intent(in)  :: n    !< Number of points.
   real(R8P), intent(out) :: x(n) !< Nodes, ascending.
   real(R8P), intent(out) :: w(n) !< Weights.
   real(R8P), parameter   :: pi = acos(-1._R8P) !< Pi.
   real(R8P)              :: z    !< Root estimate.
   real(R8P)              :: p    !< P_n(z).
   real(R8P)              :: dp   !< P_n'(z).
   integer                :: i, step !< Counters.

   do i = 1, (n + 1) / 2
      z = cos(pi * (i - 0.25_R8P) / (n + 0.5_R8P))
      do step = 1, 100
         call legendre(n, z, p, dp)
         z = z - p / dp
         if (abs(p / dp) < 1.e-15_R8P) exit
      enddo
      call legendre(n, z, p, dp) ! the derivative at the root itself, for the weight
      x(i) = -z
      x(n + 1 - i) = z
      w(i) = 2._R8P / ((1._R8P - z * z) * dp * dp)
      w(n + 1 - i) = w(i)
   enddo
   endsubroutine gauss_nodes

   pure subroutine legendre(n, z, p, dp)
   !< P_n(z) and its derivative, by the three-term recurrence.
   integer,   intent(in)  :: n  !< Degree.
   real(R8P), intent(in)  :: z  !< Abscissa.
   real(R8P), intent(out) :: p  !< P_n(z).
   real(R8P), intent(out) :: dp !< P_n'(z).
   real(R8P)              :: p1, p2 !< P_(j-1), P_(j-2).
   integer                :: j  !< Counter.

   p = 1._R8P
   p1 = 0._R8P
   do j = 1, n
      p2 = p1
      p1 = p
      p = ((2 * j - 1) * z * p1 - (j - 1) * p2) / j
   enddo
   dp = n * (z * p - p1) / (z * z - 1._R8P)
   endsubroutine legendre
endmodule gauss_legendre
