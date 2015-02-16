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


def get_parsed_files_list():
  """
  Function for creating the list of parsed files

  Returns
  -------
  list
    list of ParsedFile objects
  """
  pfiles = []
  # parsing files loop
  for root, subfolders, files in os.walk(__config__.cliargs.src):
    for filename in files:
      if any(os.path.splitext(os.path.basename(filename))[1] == ext for ext in __config__.extensions_parsed):
        if os.path.basename(filename) not in [os.path.basename(exc) for exc in __config__.cliargs.exclude]:
          filen = os.path.join(root, filename)
          pfile = ParsedFile(name=filen)
          pfile.parse()
          pfiles.append(pfile)
  return pfiles


def build():
  """
  Function for building project
  """
  builder = Builder(compiler=__config__.cliargs.compiler,
                    fc=__config__.cliargs.fc,
                    cflags=__config__.cliargs.cflags,
                    lflags=__config__.cliargs.lflags,
                    preproc=__config__.cliargs.preproc,
                    modsw=__config__.cliargs.modsw,
                    mpi=__config__.cliargs.mpi,
                    build_dir=__config__.cliargs.build_dir,
                    obj_dir=__config__.cliargs.obj_dir,
                    mod_dir=__config__.cliargs.mod_dir,
                    lib_dir=__config__.cliargs.lib_dir,
                    dinc=__config__.cliargs.include,
                    libs=__config__.cliargs.libs,
                    ext_libs=__config__.cliargs.ext_libs,
                    colors=__config__.cliargs.colors,
                    quiet=__config__.cliargs.quiet,
                    jobs=__config__.cliargs.jobs,
                    preform=__config__.cliargs.preform,
                    pfm_dir=__config__.cliargs.pfm_dir,
                    pfm_ext=__config__.cliargs.pfm_ext)
  pfiles = get_parsed_files_list()
  # building dependencies hierarchy
  __config__.check_cflags_heritage()
  if __config__.cliargs.cflags_heritage:
    dependency_hiearchy(builder=builder, pfiles=pfiles, force_compile=__config__.force_compile)
  else:
    dependency_hiearchy(builder=builder, pfiles=pfiles)
  # compiling independent files that are libraries of procedures not contained into a module (old Fortran style)
  nomodlibs = []
  for pfile in pfiles:
    if pfile.nomodlib:
      builder.build(file_to_build=pfile)
      nomodlibs.append(pfile.basename + ".o")
  # building target or all programs found
  for pfile in pfiles:
    if __config__.cliargs.target:
      if os.path.basename(__config__.cliargs.target) == os.path.basename(pfile.name):
        print(__config__.colors.bld + builder.verbose() + __config__.colors.end)
        if pfile.program:
          remove_other_main(builder=builder, pfiles=pfiles, mysefl=pfile)
        builder.build(file_to_build=pfile, output=__config__.cliargs.output, nomodlibs=nomodlibs, mklib=__config__.cliargs.mklib)
        if __config__.cliargs.log:
          pfile.save_build_log(builder=builder)
    else:
      if pfile.program:
        print(__config__.colors.bld + builder.verbose() + __config__.colors.end)
        remove_other_main(builder=builder, pfiles=pfiles, mysefl=pfile)
        builder.build(file_to_build=pfile, output=__config__.cliargs.output, nomodlibs=nomodlibs)
        if __config__.cliargs.log:
          pfile.save_build_log(builder=builder)
  return


def clean():
  """
  Function for cleaning project
  """
  cleaner = Cleaner(build_dir=__config__.cliargs.build_dir,
                    obj_dir=__config__.cliargs.obj_dir,
                    mod_dir=__config__.cliargs.mod_dir,
                    target=__config__.cliargs.target,
                    output=__config__.cliargs.output,
                    mklib=__config__.cliargs.mklib)
  if not __config__.cliargs.only_obj and not __config__.cliargs.only_target:
    cleaner.clean_mod()
    cleaner.clean_obj()
    cleaner.clean_target()
  if __config__.cliargs.only_obj:
    cleaner.clean_mod()
    cleaner.clean_obj()
  if __config__.cliargs.only_target:
    cleaner.clean_target()
  return


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
      clean()
    if __config__.cliargs.which == 'build':
      build()
  sys.exit(0)

if __name__ == '__main__':
  main()
