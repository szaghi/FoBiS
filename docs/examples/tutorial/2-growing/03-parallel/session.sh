show openmp 'fobis build --mode openmp'
show sweep 'OMP_NUM_THREADS=4 ./build/openmp/sweep'
eval "${DOCS_MPI_SETUP:-}"
needs mpif90 mpirun
show mpi 'fobis build --mode mpi --quiet'
show mpirun 'mpirun -np 2 ./build/mpi/integrate_mpi && mpirun -np 4 ./build/mpi/integrate_mpi'
