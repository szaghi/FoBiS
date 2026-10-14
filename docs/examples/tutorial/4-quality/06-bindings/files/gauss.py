"""The 3-point Gauss-Legendre rule, from Fortran, through the generated ctypes wrapper."""

import sys

sys.path.insert(0, "bindings")
import quad  # noqa: E402  (bindings/quad.py, written by fobis bindings)

quad.load("build/python/libquad_c.so")
x, w = quad.gauss_nodes(3, [0.0] * 3, [0.0] * 3)
print("nodes  ", " ".join(f"{v:+.15f}" for v in x))
print("weights", " ".join(f"{v:.15f}" for v in w))
# exact up to degree 2n - 1 = 5: the integral of x**4 on [-1, 1] is 2/5
print("integral of x**4:", sum(wi * xi**4 for xi, wi in zip(x, w, strict=True)))
