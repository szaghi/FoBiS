"""
utils.py, module definition of FoBiS.py util functions.
"""
# Copyright (C) 2015  Stefano Zaghi
#
# This file is part of FoBiS.py.
#
# FoBiS.py is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# FoBiS.py is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with FoBiS.py. If not, see <http://www.gnu.org/licenses/>.
from __future__ import print_function
import os
import subprocess
import sys


def print_fake(input_obj, end='\n'):
  """Rename print."""
  print(input_obj, end=end)


def syswork(cmd):
  """
  Function for executing system command 'cmd': for compiling and linking files.
  """
  error = 0
  try:
    output = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT)
  except subprocess.CalledProcessError as err:
    error = err.returncode
    output = err.output
  if sys.version_info[0] > 2:
    output = str(output, encoding='UTF-8')
  return [error, str(output)]


def traverse_recursive(parsed_file, path=None):
  """
  The function traverse_recursive performs a yield-recursive traversing of pfile direct dependencies.
  """
  if path is None:
    path = list()
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
  Find the parsed file containing the desidered module.

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


def dependency_hiearchy(builder, pfiles, print_w=None, force_compile=False):
  """
  Build parsed files hierarchy.

  Paramters
  ---------
  builder : Builder object
  pfiles : list
    list of ParsedFile objects
  print_w : function
    function for printing emphized warning message
  force_compile : {False}
    flag for forcing (re-)compiling of all dependency
  """
  if print_w is None:
    print_wm = print_fake
  else:
    print_wm = print_w

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
            for _, _, files in os.walk(dinc):
              for filename in files:
                if os.path.splitext(os.path.basename(filename))[0].lower() == dep.name.lower() and os.path.splitext(os.path.basename(filename))[1].lower() == '.mod':
                  fnum = 0
                  break
              if fnum == 0:
                break
            if fnum == 0:
              break
          if fnum != 0:
            print_wm("Attention: the file '" + parsed_file.name + "' depends on '" + dep.name + "' that is unreachable")
            # sys.exit(1)
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
          print_wm("Attention: the file '" + parsed_file.name + "' depends on '" + dep.name + "' that is unreachable")
          # sys.exit(1)
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


def check_results(results, log=None, print_w=None):
  """
  Check the result of system commands exectution.

  Parameters
  ----------
  results : list
    list of exectuions results
  log : {False}
    bool for activate errors log saving
  print_w : {None}
    function for printing emphized warning message
  """
  if print_w is None:
    print_wm = print_fake
  else:
    print_wm = print_w

  if not all(v[1] == '' for v in results):
    for result in results:
      if result[1] != '':
        print_wm(result[1])
  if not all(v[0] == 0 for v in results):
    for result in results:
      if result[0] != 0:
        sys.stderr.write(result[1])
        if log:
          with open(log, 'a') as logerror:
            logerror.writelines(result[1])
    sys.exit(1)


def safe_mkdir(directory, print_w=None):
  """
  Create directory via safe checkings.

  Parameters
  ----------
  directory: str
    path of the directory to be created
  print_w : {None}
    function for printing emphized warning message
  """
  if print_w is None:
    print_wm = print_fake
  else:
    print_wm = print_w

  if os.path.exists(directory):
    if not os.path.isdir(directory):
      print_wm('Error: cannot create directory "' + directory + '", a file with the same name already exists!')
      sys.exit(1)
  else:
    os.makedirs(directory)
  return
