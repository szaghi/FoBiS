FC ?= gfortran
PREFIX ?= /usr/local

all: libdemo.a

libdemo.a: src/demo.f90
	$(FC) -c -O2 src/demo.f90
	ar rcs libdemo.a demo.o

install: all
	mkdir -p $(PREFIX)/lib $(PREFIX)/include
	cp libdemo.a $(PREFIX)/lib/
	cp demo.mod $(PREFIX)/include/
