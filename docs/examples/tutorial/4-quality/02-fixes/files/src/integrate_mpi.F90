!< Simpson's rule over [0, pi] split among the MPI processes: each integrates its piece, rank 0 adds them up.
program integrate_mpi
!< Simpson's rule over [0, pi] split among the MPI processes: each integrates its piece, rank 0 adds them up.
use mpi ! fobis: ignore[COR040] the mpi module's names are all prefixed mpi_
use quad_rules, only : R8P, simpson
use integrands, only : sine
implicit none
real(R8P), parameter :: pi = acos(-1._R8P) !< Pi.
integer,   parameter :: n = 64             !< Intervals of each piece.
real(R8P)            :: a, b               !< Bounds of this process's piece.
real(R8P)            :: piece              !< Integral over this process's piece.
real(R8P)            :: total              !< Sum of the pieces.
integer              :: rank, size, ierr   !< MPI rank, number of processes, error code.

call mpi_init(ierr)
call mpi_comm_rank(mpi_comm_world, rank, ierr)
call mpi_comm_size(mpi_comm_world, size, ierr)
a = pi * rank / size
b = pi * (rank + 1) / size
piece = simpson(sine, a, b, n)
call mpi_reduce(piece, total, 1, mpi_double_precision, mpi_sum, 0, mpi_comm_world, ierr)
if (rank == 0) print '(I0, A, I0, A, ES12.4)', size, ' processes x ', n, ' intervals, error ', abs(total - 2._R8P)
call mpi_finalize(ierr)
endprogram integrate_mpi
