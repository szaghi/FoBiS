#!/usr/bin/env python
"""
FoBiS.py, Fortran Building System for poor men
"""
# modules loading
import sys
import os

from .Builder import Builder
from .Cleaner import Cleaner
from .ParsedFile import ParsedFile
from .config import __config__
from .fobos import Fobos
from .utils import dependency_hiearchy
from .utils import remove_other_main


def main():
  """
  Main function.
  """
  __config__.get_cli()
  if __config__.cliargs.fobos:
    __fobos__ = Fobos(filename=__config__.cliargs.fobos)
  else:
    __fobos__ = Fobos()
  if __config__.cliargs.which == 'rule':
    if __config__.cliargs.list:
      __fobos__.rules_list()
    elif __config__.cliargs.execute:
      __fobos__.rule_execute(rule=__config__.cliargs.execute)
  else:
    if __config__.cliargs.lmodes:
      __fobos__.modes_list()
    if __config__.cliargs.which == 'clean':
      __cleaner__ = Cleaner(build_dir=__config__.cliargs.build_dir,
                            obj_dir=__config__.cliargs.obj_dir,
                            mod_dir=__config__.cliargs.mod_dir,
                            target=__config__.cliargs.target,
                            output=__config__.cliargs.output,
                            mklib=__config__.cliargs.mklib)
      if not __config__.cliargs.only_obj and not __config__.cliargs.only_target:
        __cleaner__.clean_mod()
        __cleaner__.clean_obj()
        __cleaner__.clean_target()
      if __config__.cliargs.only_obj:
        __cleaner__.clean_mod()
        __cleaner__.clean_obj()
      if __config__.cliargs.only_target:
        __cleaner__.clean_target()
    if __config__.cliargs.which == 'build':
      __builder__ = Builder(compiler=__config__.cliargs.compiler,
                            fc=__config__.cliargs.fc,
                            modsw=__config__.cliargs.modsw,
                            mpi=__config__.cliargs.mpi,
                            cflags=__config__.cliargs.cflags,
                            lflags=__config__.cliargs.lflags,
                            libs=__config__.cliargs.libs,
                            dinc=__config__.cliargs.include,
                            preproc=__config__.cliargs.preproc,
                            build_dir=__config__.cliargs.build_dir,
                            obj_dir=__config__.cliargs.obj_dir,
                            mod_dir=__config__.cliargs.mod_dir,
                            quiet=__config__.cliargs.quiet,
                            colors=__config__.cliargs.colors,
                            jobs=__config__.cliargs.jobs,
                            preform=__config__.cliargs.preform,
                            pfm_dir=__config__.cliargs.pfm_dir,
                            pfm_ext=__config__.cliargs.pfm_ext)
      __pfiles__ = []  # main parsed files list
      # parsing files loop
      for root, subfolders, files in os.walk(__config__.cliargs.src):
        for filename in files:
          if any(os.path.splitext(os.path.basename(filename))[1] == ext for ext in __config__.extensions_parsed):
            if os.path.basename(filename) not in [os.path.basename(exc) for exc in __config__.cliargs.exclude]:
              file = os.path.join(root, filename)
              pfile = ParsedFile(name=file)
              pfile.parse()
              __pfiles__.append(pfile)
      # building dependencies hierarchy
      dependency_hiearchy(builder=__builder__, pfiles=__pfiles__)
      # compiling independent files that are libraries of procedures not contained into a module (old Fortran style)
      __nomodlibs__ = []
      for pfile in __pfiles__:
        if pfile.nomodlib:
          __builder__.build(file_to_build=pfile)
          __nomodlibs__.append(pfile.basename + ".o")
      # building target or all programs found
      for pfile in __pfiles__:
        if __config__.cliargs.target:
          if os.path.basename(__config__.cliargs.target) == os.path.basename(pfile.name):
            print(__config__.colors.bld + __builder__.verbose() + __config__.colors.end)
            if pfile.program:
              remove_other_main(builder=__builder__, pfiles=__pfiles__, mysefl=pfile)
            __builder__.build(file_to_build=pfile, output=__config__.cliargs.output, nomodlibs=__nomodlibs__, mklib=__config__.cliargs.mklib)
            if __config__.cliargs.log:
              pfile.save_build_log(builder=__builder__)
        else:
          if pfile.program:
            print(__config__.colors.bld + __builder__.verbose() + __config__.colors.end)
            remove_other_main(builder=__builder__, pfiles=__pfiles__, mysefl=pfile)
            __builder__.build(file_to_build=pfile, output=__config__.cliargs.output, nomodlibs=__nomodlibs__)
            if __config__.cliargs.log:
              pfile.save_build_log(builder=__builder__)
  sys.exit(0)

if __name__ == '__main__':
  main()
