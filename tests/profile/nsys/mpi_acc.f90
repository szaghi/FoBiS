program mpi_acc
use mpi_f08
use openacc
implicit none
integer, parameter :: n = 2000000
double precision, allocatable :: y(:)
double precision :: part, total
integer :: rank, nranks, i, ndev
call MPI_Init()
call MPI_Comm_rank(MPI_COMM_WORLD, rank)
call MPI_Comm_size(MPI_COMM_WORLD, nranks)
ndev = acc_get_num_devices(acc_device_nvidia)
call acc_set_device_num(mod(rank, max(ndev, 1)), acc_device_nvidia)
allocate(y(n * (rank + 1)))
y = 1d0
part = 0d0
!$acc parallel loop copyin(y) reduction(+:part)
do i = 1, size(y)
  part = part + y(i)
end do
call MPI_Allreduce(part, total, 1, MPI_DOUBLE_PRECISION, MPI_SUM, MPI_COMM_WORLD)
if (rank == 0) print '(a,es23.16)', 'total = ', total
call MPI_Finalize()
end program mpi_acc
