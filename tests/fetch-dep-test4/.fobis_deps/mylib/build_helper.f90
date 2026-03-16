! This file is intentionally invalid Fortran.
! It lives inside the use=fobos dep directory and must NEVER be compiled directly.
! If exclude_dirs is working correctly this file is never reached by the source scanner.
! If exclude_dirs is broken, gfortran will fail on the line below and the test will fail.
THIS LINE IS NOT VALID FORTRAN AND WILL CAUSE A COMPILATION ERROR
