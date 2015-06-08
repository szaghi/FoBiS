"""
Builder.py, module definition of Builder class.
This is a class designed for controlling the building phase.
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
try:
  from multiprocessing import Pool
  __parallel__ = True
except ImportError:
  print("Module 'multiprocessing' not found: parallel compilation disabled")
  __parallel__ = False
import operator
import os
import sys
from .Compiler import Compiler
from .utils import check_results, print_fake, syswork, safe_mkdir


class Builder(object):
  """Builder is an object that handles the building system, its attributes and methods.

  Attributes
  ----------
  s_compilers : dict
    supported compilers data
  """
  # s_compilers = {'gnu': ['gfortran', 'mpif90', '-J ', ['-ftest-coverage -fprofile-arcs', '-fprofile-arcs'], '-pg'],
  #                'intel': ['ifort', 'mpif90', '-module ', ['-prof-gen=srcpos', ''], ''],
  #                'g95': ['g95', 'mpif90', '-fmod=', ['', ''], '']}

  def __init__(self, cliargs, print_n=None, print_w=None):
    """
    Parameters
    ----------
    cliargs : argparse object
    print_n : {None}
      function for printing normal message
    print_w : {None}
      function for printing emphized warning message

    Attributes
    ----------
    compiler : Compiler object
      compiler used
    build_dir : {"./"}
      directory containing built files
    obj_dir : {"./"}
      directory containing compiled object files
    mod_dir : {"./"}
      directory containing .mod files
    lib_dir : {None}
      list of directories searched for libraries
    dinc : {None}
      list of directories for searching included files
    libs : {None}
      list of external libraries that are not into the path: must be passed with full paths
    vlibs : {None}
      list of external libraries that are not into the path and that are volatile (can changed thus triggering re-building): must be passed with full paths
    ext_libs : {None}
      list of external libraries that are into the path: are linked as '-llibrary.[a|so]' and searched into '-Ldir'
    ext_vlibs : {None}
      list of external libraries that are into the path and that are volatile (can changed thus triggering re-building): are linked as '-llibrary.[a|so]' and searched into '-Ldir'
    preform : {False}
      activate PreForM.py pre-processing
    pfm_dir : {None}
      directory containing sources processed by PreForm.py; by default are removed after used
    pfm_ext : {None}
      list of file extensions to be processed by PreForm.py; by default all files are preprocessed if PreForM.py is used
    print_n : {None}
      function for printing normal message
    print_w : {None}
      function for printing emphized warning message
    jobs : {1}
      concurrent compiling jobs
    """

    if print_n is None:
      self.print_n = print_fake
    else:
      self.print_n = print_n

    if print_w is None:
      self.print_w = print_fake
    else:
      self.print_w = print_w

    self.compiler = Compiler(cliargs=cliargs)

    self.jobs = cliargs.jobs
    self._sanitize_dirs(build_dir=cliargs.build_dir, obj_dir=cliargs.obj_dir, mod_dir=cliargs.mod_dir, lib_dir=cliargs.lib_dir, dinc=cliargs.include)
    self._sanitize_files(libs=cliargs.libs, vlibs=cliargs.vlibs, ext_libs=cliargs.ext_libs, ext_vlibs=cliargs.ext_vlibs)
    self._set_preform(preform=cliargs.preform, pfm_dir=cliargs.pfm_dir, pfm_ext=cliargs.pfm_ext)

    self.cmd_comp = self.compiler.compile_cmd(mod_dir=self.mod_dir)
    self.cmd_link = self.compiler.link_cmd(mod_dir=self.mod_dir)
    return

  @staticmethod
  def get_fc(cliargs):
    """
    Method for getting the compiler command built accordingly to the cli arguments.

    Parameters
    ----------
    cliargs : argparse object
    """
    return Compiler(cliargs=cliargs).fcs

  @staticmethod
  def get_cflags(cliargs):
    """
    Method for getting the compiling flags built accordingly to the cli arguments.

    Parameters
    ----------
    cliargs : argparse object
    """
    return Compiler(cliargs=cliargs).cflags

  @staticmethod
  def get_lflags(cliargs):
    """
    Method for getting the linking flags built accordingly to the cli arguments.

    Parameters
    ----------
    cliargs : argparse object
    """
    return Compiler(cliargs=cliargs).lflags

  @staticmethod
  def get_modsw(cliargs):
    """
    Method for getting the compiler modules switch built accordingly to the cli arguments.

    Parameters
    ----------
    cliargs : argparse object
    """
    # modsw = cliargs.modsw
    # if cliargs.compiler.lower() in Builder.s_compilers and modsw == '':
    #   modsw = Builder.s_compilers[cliargs.compiler.lower()][2]
    # return modsw
    return Compiler(compiler=cliargs.compiler, modsw=cliargs.modsw).modsw

  def _sanitize_dirs(self, build_dir, obj_dir, mod_dir, lib_dir, dinc):
    """
    Method for sanitizing directory paths.

    Parameters
    ----------
    build_dir : str
      directory containing built files
    obj_dir : str
      directory containing compiled object files
    mod_dir : str
      directory containing .mod files
    lib_dir : list
      list of directories searched for libraries
    dinc : list
      list of directories for searching included files
    """
    self.build_dir = os.path.normpath(build_dir)
    safe_mkdir(directory=self.build_dir, print_w=self.print_w)

    self.obj_dir = os.path.normpath(os.path.join(build_dir, obj_dir))
    safe_mkdir(directory=self.obj_dir, print_w=self.print_w)

    self.mod_dir = os.path.normpath(os.path.join(build_dir, mod_dir))
    safe_mkdir(directory=self.mod_dir, print_w=self.print_w)

    if lib_dir is None:
      self.lib_dir = []
    else:
      self.lib_dir = lib_dir
      for directory in self.lib_dir:
        directory = os.path.normpath(directory)
    if dinc is None:
      self.dinc = []
    else:
      self.dinc = dinc
      for directory in self.dinc:
        directory = os.path.normpath(directory)
    return

  def _sanitize_files(self, libs, vlibs, ext_libs, ext_vlibs):
    """
    Method for sanitizing files paths.

    Parameters
    ----------
    libs : list
      list of external libraries that are not into the path: must be passed with full paths
    vlibs : list
      list of external libraries that are not into the path and that are volatile (can changed thus triggering re-building): must be passed with full paths
    ext_libs : list
      list of external libraries that are into the path: are linked as '-llibrary.[a|so]' and searched into '-Ldir'
    ext_vlibs : list
      list of external libraries that are into the path and that are volatile (can changed thus triggering re-building): are linked as '-llibrary.[a|so]' and searched into '-Ldir'
    """
    if libs is None:
      self.libs = []
    else:
      self.libs = libs
      for lib in self.libs:
        lib = os.path.normpath(lib)
    if vlibs is None:
      self.vlibs = []
    else:
      self.vlibs = vlibs
      for lib in self.vlibs:
        lib = os.path.normpath(lib)
    if ext_libs is None:
      self.ext_libs = []
    else:
      self.ext_libs = ext_libs
      for lib in self.ext_libs:
        lib = os.path.normpath(lib)
    if ext_vlibs is None:
      self.ext_vlibs = []
    else:
      self.ext_vlibs = ext_vlibs
      for lib in self.ext_vlibs:
        lib = os.path.normpath(lib)
    return

  def _set_preform(self, preform, pfm_dir, pfm_ext):
    """
    Method for safetely setting PreForM.py data.

    Parameters
    ----------
    preform : bool
      activate PreForM.py pre-processing
    pfm_dir : str
      directory containing sources processed by PreForm.py; by default are removed after used
    pfm_ext : list
      list of file extensions to be processed by PreForm.py; by default all files are preprocessed if PreForM.py is used
    """
    self.preform = preform
    if pfm_ext is None:
      self.pfm_ext = []
    else:
      self.pfm_ext = pfm_ext
    self.pfm_dir = pfm_dir
    if self.pfm_dir:
      self.pfm_dir = os.path.normpath(os.path.join(self.build_dir, self.pfm_dir))
      if not os.path.exists(self.pfm_dir):
        os.makedirs(self.pfm_dir)
    if self.preform:
      pfm_exist = False
      for path in os.environ["PATH"].split(os.pathsep):
        pfm_exist = os.path.exists(os.path.join(path, 'PreForM.py'))
        if pfm_exist:
          break
      if not pfm_exist:
        self.print_w('Error: PreForM.py is not in your PATH! You cannot use --preform or -pfm switches.')
    return

  def _compile_preform(self, file_to_compile):
    """
    Method for creating compile command with PreForM.py usage.

    Parameters
    ----------
    file_to_compile : ParsedFile object
      file to be compiled

    Returns
    -------
    str
      string containing the PreForM.py command
    str
      string containing the output file name of PreForM.py
    str
      string containing the command for removing/storing PreForM.py outputs
    """
    preform_cmd = ''
    preform_output = ''
    preform_remove = ''
    to_preform = False
    if self.preform:
      if len(self.pfm_ext) > 0:
        if file_to_compile.extension in self.pfm_ext:
          to_preform = True
      else:
        to_preform = True
      if to_preform and self.pfm_dir:
        pfm_dir = self.pfm_dir
        preform_store = True
      else:
        pfm_dir = ''
        preform_store = False
      if to_preform:
        preform_cmd = 'PreForM.py ' + file_to_compile.name + ' -o ' + os.path.join(pfm_dir, file_to_compile.basename + '.pfm.f90') + ' ; '
        preform_output = os.path.join(pfm_dir, file_to_compile.basename + '.pfm.f90')
        if not preform_store:
          preform_remove = ' ; rm -f ' + preform_output
    return preform_cmd, preform_output, preform_remove

  def _compile_include(self):
    """
    Method for creating compile command with inluded paths.

    Returns
    -------
    str
      string containing the include command
    """
    include_cmd = ''
    if len(self.dinc) > 0:
      include_cmd = ''.join(['-I' + s + ' ' for s in self.dinc])
    return include_cmd

  def _compile_command(self, file_to_compile):
    """
    Method for returning the OS command for compiling file_to_compile.

    Parameters
    ----------
    file_to_compile : ParsedFile object
      file to be compiled

    Returns
    -------
    str
      string containing the compile command
    """
    preform_cmd, preform_output, preform_remove = self._compile_preform(file_to_compile)
    include_cmd = self._compile_include()

    if preform_cmd != '':
      comp_cmd = preform_cmd + self.cmd_comp + ' ' + include_cmd + preform_output + ' -o ' + os.path.join(self.obj_dir, file_to_compile.basename + '.o') + preform_remove
    else:
      comp_cmd = self.cmd_comp + ' ' + include_cmd + file_to_compile.name + ' -o ' + os.path.join(self.obj_dir, file_to_compile.basename + '.o')
    return comp_cmd

  def _link_command(self, file_to_build, output=None, nomodlibs=None):
    """
    Method for returning the OS command for linkng file_to_build.

    Parameters
    ----------
    file_to_build : ParsedFile object
      file to be built
    output : str
      output name
    nomodlibs : {None}
      list of old-Fortran style libraries objects

    Returns
    -------
    str
      string containing the link command
    """
    if nomodlibs is not None:
      objs = nomodlibs + file_to_build.obj_dependencies()
    else:
      objs = file_to_build.obj_dependencies()
    if output:
      exe = os.path.join(self.build_dir, output)
    else:
      exe = os.path.join(self.build_dir, file_to_build.basename)
    link_cmd = self.cmd_link + " " + "".join([os.path.join(self.obj_dir, s + " ") for s in objs]) + "".join([s + " " for s in self.libs]) + "".join([s + " " for s in self.vlibs])
    if len(self.ext_libs) > 0:
      link_cmd += " " + "".join(["-l" + s + " " for s in self.ext_libs])
    if len(self.ext_vlibs) > 0:
      link_cmd += " " + "".join(["-l" + s + " " for s in self.ext_vlibs])
    if len(self.lib_dir) > 0:
      link_cmd += " " + "".join(["-L" + s + " " for s in self.lib_dir])
    link_cmd += " -o " + exe
    return link_cmd, exe

  def _mklib_command(self, file_to_build, output=None, nomodlibs=None, mklib=None):
    """
    Method for returning the OS command for linkng file_to_build as a library.

    Parameters
    ----------
    file_to_build : ParsedFile object
      file to be built
    output : str
      output name
    nomodlibs : {None}
      list of old-Fortran style libraries objects
    mklib : {None}
      bool for activate building library mode

    Returns
    -------
    str
      string containing the link command
    """
    if nomodlibs is not None:
      objs = nomodlibs + file_to_build.obj_dependencies(exclude_programs=True)
    else:
      objs = file_to_build.obj_dependencies(exclude_programs=True)
    if output:
      lib = os.path.join(self.build_dir, output)
    else:
      if mklib.lower() == 'shared':
        lib = os.path.join(self.build_dir, file_to_build.basename + '.so')
      elif mklib.lower() == 'static':
        lib = os.path.join(self.build_dir, file_to_build.basename + '.a')
    if mklib.lower() == 'shared':
      link_cmd = self.cmd_link + " " + "".join([os.path.join(self.obj_dir, s + " ") for s in objs]) + "".join([s + " " for s in self.libs]) + "".join([s + " " for s in self.vlibs]) + " -o " + lib
    elif mklib.lower() == 'static':
      link_cmd = "ar -rcs " + lib + " " + "".join([os.path.join(self.obj_dir, s + " ") for s in objs]) + "".join([s + " " for s in self.libs]) + "".join([s + " " for s in self.vlibs]) + " ; ranlib " + lib
    return link_cmd, lib

  def _get_hierarchy(self, file_to_build):
    """
    Method for creating a hierarchy of compiling commands accordingly to the dependencies order.

    Parameters
    ----------
    file_to_build : ParsedFile
    """
    order_max = max([p for p in file_to_build.pfile_dep_all if not p.include and p.to_compile], key=operator.attrgetter('order')).order + 1
    hierarchy = [[] for _ in range(order_max)]
    for dep in file_to_build.pfile_dep_all:
      if dep.to_compile and not dep.include:
        hierarchy[dep.order].append([dep.name, self._compile_command(file_to_compile=dep)])
        dep.to_compile = False
    hierarchy = [h for h in hierarchy if len(h) > 0]
    return hierarchy

  def _compile(self, file_to_build, verbose=False, log=False):
    """
    Method for actually compiling files.

    Parameters
    ----------
    file_to_build : ParsedFile
    verbose : {False}
      bool for activate extreme verbose outputs
    log : {False}
      bool for activate errors log saving
    """
    hierarchy = self._get_hierarchy(file_to_build)
    for deps in reversed(hierarchy):
      files_to_compile = ''
      cmds = []
      for dep in deps:
        files_to_compile = files_to_compile + " " + dep[0]
        cmds.append(dep[1])
      if len(deps) > 1 and self.jobs > 1 and __parallel__:
        jobs = min(len(deps), self.jobs)
        self.print_n("Compiling" + files_to_compile + " using " + str(jobs) + " concurrent processes")
        if verbose:
          self.print_n("Executing: " + str(cmds))
        pool = Pool(processes=jobs)
        results = pool.map(syswork, cmds)
        pool.close()
        pool.join()
      else:
        self.print_n("Compiling" + files_to_compile + " serially")
        results = []
        for cmd in cmds:
          if verbose:
            self.print_n("Executing: " + str(cmd))
          result = syswork(cmd)
          results.append(result)
      if log:
        check_results(results=results, log="building-errors.log", print_w=self.print_w)
      else:
        check_results(results=results, print_w=self.print_w)
    return

  def gnu_make_variables(self):
    """
    Method returing the builder options formated as GNU Make variables

    Returns
    -------
    str
      string containing the builder options in GNU Make format
    """
    string = []
    string.append("DOBJ    = " + os.path.normpath(self.obj_dir) + "/\n")
    string.append("DMOD    = " + os.path.normpath(self.mod_dir) + "/\n")
    string.append("DEXE    = " + os.path.normpath(self.build_dir) + "/\n")
    libs = []
    if len(self.libs) > 0:
      libs += self.libs
    if len(self.vlibs) > 0:
      libs += self.vlibs
    if len(self.ext_libs) > 0:
      libs += ["-l" + l + " " for l in self.ext_libs]
    if len(self.ext_vlibs) > 0:
      libs += ["-l" + l + " " for l in self.ext_vlibs]
    if len(self.lib_dir) > 0:
      libs += ["-L" + l + " " for l in self.lib_dir]
    if len(libs) > 0:
      string.append("LIBS    = " + "".join(" " + l for l in libs) + "\n")
    else:
      string.append("LIBS    =\n")
    string.append("FC      = " + self.compiler.fcs + "\n")
    string.append("OPTSC   = " + self.compiler.cflags + " " + self.compiler.modsw + self.mod_dir + "\n")
    string.append("OPTSL   = " + self.compiler.lflags + " " + self.compiler.modsw + self.mod_dir + "\n")
    return "".join(string)

  def build(self, file_to_build, output=None, nomodlibs=None, mklib=None, verbose=False, log=False):
    """
    Method for building file.

    Parameters
    ----------
    file_to_build : ParsedFile
    output : str
      output name
    nomodlibs : {None}
      list of old-Fortran style libraries objects
    mklib : {None}
      bool for activate building library mode
    verbose : {False}
      bool for activate extreme verbose outputs
    log : {False}
      bool for activate errors log saving
    """
    self.print_n('Building ' + file_to_build.name)
    # sort dependencies accordingly to indirect dependency
    file_to_build.sort_dependencies()
    # creating a hierarchy list of compiling commands accordingly to the order of all dependencies
    if len([p for p in file_to_build.pfile_dep_all if not p.include and p.to_compile]) > 0:
      self._compile(file_to_build=file_to_build, verbose=verbose, log=log)
    else:
      self.print_n('Nothing to compile, all objects are up-to-date')
    if file_to_build.program:
      link_cmd, exe = self._link_command(file_to_build=file_to_build, output=output, nomodlibs=nomodlibs)
      self.print_n("Linking " + exe)
      if verbose:
        self.print_n("Executing: " + str(link_cmd))
      result = syswork(link_cmd)
      if log:
        check_results(results=[result], log="building-errors.log", print_w=self.print_w)
      else:
        check_results(results=[result], print_w=self.print_w)
      self.print_n('Target ' + file_to_build.name + ' has been successfully built')
    elif mklib:
      link_cmd, lib = self._mklib_command(file_to_build=file_to_build, output=output, nomodlibs=nomodlibs, mklib=mklib)
      self.print_n("Linking " + lib)
      if verbose:
        self.print_n("Executing: " + str(link_cmd))
      result = syswork(link_cmd)
      if log:
        check_results(results=[result], log="building-errors.log", print_w=self.print_w)
      else:
        check_results(results=[result], print_w=self.print_w)
      self.print_n('Target ' + file_to_build.name + ' has been successfully built')
    return

  def verbose(self, quiet=False):
    """
    The method verbose returns a verbose message containing builder infos.

    Parameters
    ----------
    quiet : {False}
      flag for making less verbose outputs
    """
    message = ''
    if not quiet:
      message = "Builder options" + "\n"
      message += "  Directories\n"
      message += '    Building directory: "' + self.build_dir + '"\n'
      message += '    Compiled-objects .o   directory: "' + self.obj_dir + '"\n'
      message += '    Compiled-objects .mod directory: "' + self.mod_dir + '"\n'
      if len(self.lib_dir) > 0:
        message += "  External libraries directories: " + "".join([s + " " for s in self.lib_dir]) + "\n"
      if len(self.dinc) > 0:
        message += "  Included paths: " + "".join([s + " " for s in self.dinc]) + "\n"
      if len(self.libs) > 0:
        message += "  Linked libraries with full path: " + "".join([s + " " for s in self.libs]) + "\n"
      if len(self.vlibs) > 0:
        message += "  Linked volatile libraries with full path: " + "".join([s + " " for s in self.vlibs]) + "\n"
      if len(self.ext_libs) > 0:
        message += "  Linked libraries in path: " + "".join([s + " " for s in self.ext_libs]) + "\n"
      if len(self.ext_vlibs) > 0:
        message += "  Linked volatile libraries in path: " + "".join([s + " " for s in self.ext_vlibs]) + "\n"
      message += self.compiler.pprint(prefix='  ')
      message += "  PreForM.py used: " + str(self.preform) + "\n"
      message += "  PreForM.py output directory: " + str(self.pfm_dir) + "\n"
      message += "  PreForM.py extensions processed: " + str(self.pfm_ext) + "\n"
    return message
