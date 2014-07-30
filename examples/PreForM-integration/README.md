# FoBiS.py PreForM.py pre-processor integration

A KISS usage example of FoBiS.py

## Description

FoBiS.py is well integrated with [PreForM.py](https://github.com/szaghi/PreForM), a powerful yet simple pre-processor mainly designed for Fortran poor-men. PreForM.py is template system (besides other things such as a `cpp-compatible` pre-processir) that is very helpful in many circumstances. In this example a Fortran program contained into `simple-for-loop.f90` is automatically built with FoBiS.py but it is pre-processed with PreForM.py, it being _polluted_ by PreForM.py pre-processing directives. To build the project just type:
```bash
FoBiS.py build --preform
```
If all goes right an program named _simple-for-loop_ is built into the directory _build_.
