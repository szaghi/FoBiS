---
title: 6. C and Python bindings
---

# 6. C and Python bindings

`quad` gets a Gauss-Legendre module: the nodes and weights of the n-point rule, exact for polynomials of degree
2n - 1:

<<< @/examples/tutorial/4-quality/06-bindings/files/src/gauss_legendre.F90{fortran}

To use it from C or Python, its procedures need a C interface: `bind(c)`, C types, no assumed shapes. `fobis
bindings` writes it, without touching the module:

<<< @/examples/output/4-quality/06/bindings.txt{console}

The rules of `quad_rules` take a function as argument: that has no C counterpart here, and the report says why they
are skipped. Three files are written: a Fortran shim module, a C header, a Python module.

::: code-group

<<< @/examples/output/4-quality/06/shim.txt{console} [quad_c.f90]

<<< @/examples/output/4-quality/06/header.txt{console} [quad.h]

:::

The shim converts each argument to and from its C type explicitly (`R8P` is a C `double` because it has 15 digits,
not because of its name) and repeats the module's `use` statements, which give the kinds. A shared library of the
shim and the modules it uses:

```ini
[python]
help      = The C and Python bindings, a shared library
template  = template-gnu
cflags    = -c -O2 -fPIC
src       = ./src/ ./bindings/
build_dir = ./build/python/
target    = bindings/quad_c.f90
mklib     = shared
output    = libquad_c.so
```

<<< @/examples/output/4-quality/06/build.txt{console}

And from Python:

<<< @/examples/tutorial/4-quality/06-bindings/files/gauss.py{python}

<<< @/examples/output/4-quality/06/python.txt{console}

The integral of x⁴ on [-1, 1] is 2/5: three points integrate it exactly, up to rounding.

::: tip What you learned
`fobis bindings MODULE...`, what can be bound and what cannot, building and calling the result. Reference:
[C and Python bindings](/cookbook/analysis#call-fortran-from-c-or-python).
:::

Next: [7. Instructions for agents](./07-agents).
