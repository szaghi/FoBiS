#!/usr/bin/env python
"""
utils.py, module definition of FoBiS.py util functions.
"""
import os
import subprocess
import sys
from .config import __config__


def syswork(cmd):
  """
  Function for executing system command 'cmd': for compiling and linking files.
  """
  error = 0
  try:
    output = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT)
    # if output:
    #   print(output)
  except subprocess.CalledProcessError as err:
    error = err.returncode
    output = err.output
  return [error, output]


def traverse_recursive(parsed_file, path=list()):
  """
  The function traverse_recursive performs a yield-recursive traversing of pfile direct dependencies.
  """
  path.append(parsed_file)
  yield path
  for dep in parsed_file.pfile_dep:
    if dep != parsed_file:
      for path in traverse_recursive(dep, path):
        yield path
  if path:
    path.pop()


def unique_seq(seq):
  """
  The function unique_seq returns the input sequence removing duplicated elements but peserving the original order.
  """
  seen = set()
  seen_add = seen.add
  return [x for x in seq if x not in seen and not seen_add(x)]


def module_is_in(pfiles, module):
  """
  Function finding the parsed file containing the desidered module.

  Parameters
  ----------
  pfiles : list
    list of parsed files
  module : str
    module name

  Returns
  -------
  file_name : str
    name of file containing the module
  number : int
    number of file containing the module
  """
  file_name = ""
  number = -1
  for fnum, parsed_file in enumerate(pfiles):
    if parsed_file.module:
      for module_name in parsed_file.module_names:
        if module_name.lower() == module.lower():
          file_name = parsed_file.name
          number = fnum
          break
  return file_name, number


def include_is_in(pfiles, include):
  """
  Function finding the parsed file containing the desidered include-file.

  Parameters
  ----------
  pfiles : list
    list of parsed files
  include : str
    include-file name

  Returns
  -------
  file_name : str
    name of file containing the include-file
  number : int
    number of file containing the include-file
  """
  file_name = ""
  number = -1
  for fnum, parsed_file in enumerate(pfiles):
    if os.path.basename(parsed_file.name) == include:
      file_name = parsed_file.name
      number = fnum
      break
  return file_name, number


def dependency_hiearchy(builder, pfiles, force_compile=False):
  """
  The function dependency_hiearchy builds parsed files hierarchy.

  Paramters
  ---------
  builder : Builder object
  pfiles : list
    list of ParsedFile objects
  force_compile : {False}
    flag for forcing (re-)compiling of all dependency
  """
  # direct dependencies list used after for building indirect (complete) dependencies list
  for parsed_file in pfiles:
    parsed_file.pfile_dep = []
    for dep in parsed_file.dependencies:
      if dep.type == "module":
        dep.file, fnum = module_is_in(pfiles=pfiles, module=dep.name)
        if fnum > -1:
          if not pfiles[fnum] in parsed_file.pfile_dep:
            parsed_file.pfile_dep.append(pfiles[fnum])
        else:
          # there is no source containg the searched module, try to find it into a precompiled mod file into eventually included paths
          for dinc in builder.dinc:
            for root, subfolders, files in os.walk(dinc):
              for filename in files:
                if os.path.splitext(os.path.basename(filename))[0].lower() == dep.name.lower() and os.path.splitext(os.path.basename(filename))[1].lower() == '.mod':
                  fnum = 0
                  break
              if fnum == 0:
                break
            if fnum == 0:
              break
          if fnum != 0:
            print(__config__.colors.red + "Attention: the file '" + parsed_file.name + "' depends on '" + dep.name + "' that is unreachable" + __config__.colors.end)
            sys.exit(1)
      if dep.type == "include":
        dep.file, fnum = include_is_in(pfiles=pfiles, include=dep.name)
        if fnum > -1:
          if not pfiles[fnum] in parsed_file.pfile_dep:
            pfiles[fnum].program = False
            pfiles[fnum].module = False
            pfiles[fnum].nomodlib = False
            pfiles[fnum].include = True
            parsed_file.pfile_dep.append(pfiles[fnum])
            if not os.path.dirname(pfiles[fnum].name) in builder.dinc:
              builder.dinc.append(os.path.dirname(pfiles[fnum].name))
        else:
          print(__config__.colors.red + "Attention: the file '" + parsed_file.name + "' depends on '" + dep.name + "' that is unreachable" + __config__.colors.end)
          sys.exit(1)
  # indirect dependency list
  for parsed_file in pfiles:
    parsed_file.create_pfile_dep_all()
  # using the just created hiearchy for checking which files must be (re-)compiled
  for parsed_file in pfiles:
    parsed_file.check_compile(obj_dir=builder.obj_dir, force_compile=force_compile)


def remove_other_main(builder, pfiles, mysefl):
  """
  The function remove_other_main removes all compiled objects of other program than the current target under building.
  """
  for parsed_file in pfiles:
    if parsed_file.program and parsed_file.name != mysefl.name:
      if os.path.exists(builder.obj_dir + parsed_file.basename + ".o"):
        os.remove(builder.obj_dir + parsed_file.basename + ".o")
