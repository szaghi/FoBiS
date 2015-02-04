# FoBiS.py PreForM.py pre-processor integration

A KISS usage example of FoBiS.py

## Description

FoBiS.py is well integrated with [PreForM.py](https://github.com/szaghi/PreForM), a powerful yet simple pre-processor mainly designed for Fortran poor-men. PreForM.py is a template system (besides other things such as a `cpp-compatible` pre-processor) that is very helpful in many circumstances. In this example a Fortran program contained into `simple-for-loop.f90` is automatically built with FoBiS.py, but it is pre-processed with PreForM.py, it being _polluted_ by PreForM.py pre-processing directives. To build the project just type:
```bash
FoBiS.py build --preform
```
If all goes right an program named _simple-for-loop_ is built into the directory _build_.

Note that the source preprocessed by means of PreForM.py is placed into the directory `build/pfm` and only the sources with extension `.pfm` are preprocessed. This is obtained by the following fobos options:
```ini
pfm_dir = ./pfm/
pfm_ext = .pfm
```

The option `pfm_dir` specifies the directory where to place (relatively to the `build_dir`) the processed sources: if it is not specified the default behaviour is to not store the processed sources and delete them after they have been used.

The option `pfm_ext` specifies the sources extensions (it can be a list) that are actually preprocessed: if it is not specified the default behaviour is to preprocess all sources. Note that if it is specified together the `pfm_dir` option the processed sources are saved with name `basename`+`.pfm.f90` no matter the original extension is defined by `pfm_ext`.
