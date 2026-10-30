cmake_minimum_required(VERSION 3.16)
project(cmath LANGUAGES Fortran)
add_library(cmath STATIC src/cmath.f90)
install(TARGETS cmath ARCHIVE DESTINATION lib)
