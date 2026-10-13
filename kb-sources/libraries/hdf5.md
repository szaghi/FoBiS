# HDF5 from Fortran

Facts about using HDF5 from Fortran that cause wrong data, unreadable files or failed builds. "Measured" means
observed with HDF5 2.0.0 (a parallel build with the Fortran interface, built with gfortran 14.2) on Linux.

## Call h5open_f before anything else

The Fortran predefined type identifiers (`H5T_NATIVE_DOUBLE`, `H5T_NATIVE_INTEGER`, ...) are variables of the
`hdf5` module set by `h5open_f`. Before it they hold 0 (measured: `H5T_NATIVE_DOUBLE` printed 0 before
`h5open_f` and a large identifier after), so a call made earlier passes an invalid identifier to the library.
Call `h5open_f` once at start-up and `h5close_f` at the end.

## Dimensions appear reversed

HDF5 stores dataspaces in C (row-major) order. A Fortran array `rho(3, 2)` written with dimensions `[3, 2]`
appears as `( 2, 3 )` in `h5dump` (measured); the values are in the file in Fortran memory order, so element
`rho(i, j)` is `[j-1][i-1]` on the C side. Tools written in C or Python (h5py) see the transpose. FoBiS's
`hdf5` probe reports the stored (C-order) shape, and `fobis verify` labels the worst element of such a
quantity with 0-based C indices.

## The Fortran module belongs to one compiler

`use hdf5` reads the `hdf5.mod` of the installation, which only the compiler that built HDF5 can read (module
formats differ between compilers and between gfortran releases: compilers pack). Keep one HDF5 build per
compiler, and select it together with the compiler (a module system, or `ext_libs`/`include` per fobos mode).
The `h5fc` wrapper (`h5pfc` for parallel HDF5) prints the flags it adds with `h5fc -show`; the build settings
are in `lib/libhdf5.settings` of the installation (`Fortran: ON`, `Parallel HDF5: ON`).

## Parallel HDF5

A parallel build (`Parallel HDF5: ON` in `libhdf5.settings`) needs MPI at compile and link time: use the
`h5pfc` wrapper or the MPI wrapper with the HDF5 flags, and open files with an MPI-IO file access property list
(`h5pset_fapl_mpio_f`). Collective operations, and transfers set to collective with `h5pset_dxpl_mpio_f`, must be
called by every rank of the communicator, including ranks that write no data (with an empty selection); a rank
that skips the call makes the others wait.

## File locking

HDF5 locks every file it opens (since release 1.10). On file systems where the lock fails, the open fails or a
reader gets nothing; the maintainer observed Windows ParaView reading an XDMF/HDF5 dataset from a WSL share
(`\\wsl$\...`) as empty, without an error. Setting `HDF5_USE_FILE_LOCKING=FALSE` in the reader's environment
disables locking: safe for read-only viewing, unsafe when several processes write the same file. The measured
build reports `Use file locking: best-effort` in its settings (lock failures ignored where the file system does
not support locks).

## Reading HDF5 in FoBiS cases

A case quantity `name : hdf5 FILE /group/dataset` is read with h5py when it is importable, else with the
`h5dump` command; when neither is available the quantity is reported as not read, with the reason, instead of
failing silently. Load the HDF5 tools (for example with the module that provides them) before
`fobis case run` or `fobis verify`.
