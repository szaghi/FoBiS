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
from .Compiler import Compiler
from .utils import check_results, print_fake, syswork, safe_mkdir


class Builder(object):
  """Builder is an object that handles the building system, its attributes and methods."""

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
    preprocessor : {None}
      activate preprocessor
    preprocessor_dir : {None}
      directory containing sources processed by preprocessor (if any); by default are removed after used
    preprocessor_ext : {None}
      list of file extensions to be processed by preprocessor; by default all files are preprocessed if preprocessor is used
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

    self.compiler = Compiler(cliargs=cliargs, print_w=self.print_w)

    self.jobs = cliargs.jobs
    self._sanitize_dirs(build_dir=cliargs.build_dir, obj_dir=cliargs.obj_dir, mod_dir=cliargs.mod_dir, lib_dir=cliargs.lib_dir, dinc=cliargs.include)
    self._sanitize_files(libs=cliargs.libs, vlibs=cliargs.vlibs, ext_libs=cliargs.ext_libs, ext_vlibs=cliargs.ext_vlibs)
    self._set_preprocessor(preprocessor=cliargs.preprocessor, preprocessor_dir=cliargs.preprocessor_dir, preprocessor_ext=cliargs.preprocessor_ext)

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

  def _set_preprocessor(self, preprocessor, preprocessor_dir, preprocessor_ext):
    """
    Set preprocessor data.

    Parameters
    ----------
    preprocessor : bool
      activate preprocessor
    preprocessor_dir : str
      directory containing sources processed by preprocessor; by default are removed after used
    preprocessor_ext : list
      list of file extensions to be processed by preprocessor; by default all files are preprocessed if preprocessor is used
    """
    self.preprocessor = preprocessor
    if preprocessor_ext is None:
      self.preprocessor_ext = []
    else:
      self.preprocessor_ext = preprocessor_ext
    self.preprocessor_dir = preprocessor_dir
    if self.preprocessor_dir:
      self.preprocessor_dir = os.path.normpath(os.path.join(self.build_dir, self.preprocessor_dir))
      if not os.path.exists(self.preprocessor_dir):
        os.makedirs(self.preprocessor_dir)
    if self.preprocessor:
      preprocessor_exist = False
      for path in os.environ["PATH"].split(os.pathsep):
        preprocessor_exist = os.path.exists(os.path.join(path, self.preprocessor))
        if preprocessor_exist:
          break
      if not preprocessor_exist:
        self.print_w('Error: ' + self.preprocessor + ' is not in your PATH! You cannot use -preprocessor switch.')
    return

  def _compile_preprocessor(self, file_to_compile):
    """
    Create compile command with preprocessor usage.

    Parameters
    ----------
    file_to_compile : ParsedFile object
      file to be compiled

    Returns
    -------
    str
      string containing the preprocessor command
    str
      string containing the output file name of preprocessor
    str
      string containing the command for removing/storing preprocessor outputs
    """
    preprocessor_cmd = ''
    preprocessor_output = ''
    preprocessor_remove = ''
    to_preprocess = False
    if self.preprocessor:
      if len(self.preprocessor_ext) > 0:
        if file_to_compile.extension in self.preprocessor_ext:
          to_preprocess = True
      else:
        to_preprocess = True
      if to_preprocess and self.preprocessor_dir:
        preprocessor_dir = self.preprocessor_dir
        preprocessor_store = True
      else:
        preprocessor_dir = ''
        preprocessor_store = False
      if to_preprocess:
        preprocessor_cmd = self.preprocessor + ' ' + file_to_compile.name + ' -o ' + os.path.join(preprocessor_dir, file_to_compile.basename + '.pp.f90') + ' ; '
        preprocessor_output = os.path.join(preprocessor_dir, file_to_compile.basename + '.pp.f90')
        if not preprocessor_store:
          preprocessor_remove = ' ; rm -f ' + preprocessor_output
    return preprocessor_cmd, preprocessor_output, preprocessor_remove

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
    preprocessor_cmd, preprocessor_output, preprocessor_remove = self._compile_preprocessor(file_to_compile)
    include_cmd = self._compile_include()

    if preprocessor_cmd != '':
      comp_cmd = preprocessor_cmd + self.cmd_comp + ' ' + include_cmd + preprocessor_output + ' -o ' + os.path.join(self.obj_dir, file_to_compile.basename + '.o') + preprocessor_remove
    else:
      comp_cmd = self.cmd_comp + ' ' + include_cmd + file_to_compile.name + ' -o ' + os.path.join(self.obj_dir, file_to_compile.basename + '.o')
    return comp_cmd

  def _link_command(self, file_to_build, output=None, nomodlibs=None, submodules=None, mklib=None):
    """
    Return the OS command for linkng file_to_build.

    Parameters
    ----------
    file_to_build : ParsedFile object
      file to be built
    output : str
      output name
    nomodlibs : {None}
      list of old-Fortran style libraries objects
    submodules : {None}
      list of submodules objects
    mklib : {None}
      activate building library mode

    Returns
    -------
    str
      string containing the link command
    """
    exe = self.get_output_name(file_to_build=file_to_build, output=output)
    link_cmd = self.cmd_link + " " + self._get_libs_link_command(file_to_build=file_to_build, nomodlibs=nomodlibs, submodules=submodules, mklib=mklib) + " -o " + exe
    return link_cmd, exe

  def _mklib_command(self, file_to_build, output=None, nomodlibs=None, submodules=None, mklib=None):
    """
    Return the OS command for linkng file_to_build as a library.

    Parameters
    ----------
    file_to_build : ParsedFile object
      file to be built
    output : str
      output name
    nomodlibs : {None}
      list of old-Fortran style libraries objects
    submodules : {None}
      list of submodules objects
    mklib : {None}
      activate building library mode

    Returns
    -------
    str
      string containing the link command
    """
    lib = self.get_output_name(file_to_build=file_to_build, output=output, mklib=mklib)
    link_cmd = self._get_libs_link_command(file_to_build=file_to_build, exclude_programs=True, nomodlibs=nomodlibs, submodules=submodules, mklib=mklib)
    if mklib is not None:
      if mklib.lower() == 'shared':
        link_cmd = self.cmd_link + " " + link_cmd + " -o " + lib
      elif mklib.lower() == 'static':
        link_cmd = "ar -rcs " + lib + " " + link_cmd + " \n ranlib " + lib
    return link_cmd, lib

  def _get_libs_link_command(self, file_to_build, exclude_programs=False, nomodlibs=None, submodules=None, mklib=None):
    """
    Return the libraries link command

    Parameters
    ----------
    file_to_build : ParsedFile object
      file to be built
    exclude_programs : {False}
      flag for excluding programs obj from the list
    nomodlibs : {None}
      list of old-Fortran style libraries objects
    submodules : {None}
      list of submodules objects
    mklib : {None}
      activate building library mode

    Returns
    -------
    str
      string containing the link command
    """
    objs = []
    if nomodlibs is not None:
      objs = objs + nomodlibs
    if submodules is not None:
      objs = objs + submodules
    objs = objs + file_to_build.obj_dependencies(exclude_programs=exclude_programs)
    link_cmd = "".join([os.path.join(self.obj_dir, s + " ") for s in objs]) + "".join([s + " " for s in self.libs]) + "".join([s + " " for s in self.vlibs])
    if mklib is None or mklib.lower() == 'shared':
      if len(self.ext_libs) > 0:
        link_cmd += " " + "".join(["-l" + s + " " for s in self.ext_libs])
      if len(self.ext_vlibs) > 0:
        link_cmd += " " + "".join(["-l" + s + " " for s in self.ext_vlibs])
      if len(self.lib_dir) > 0:
        link_cmd += " " + "".join(["-L" + s + " " for s in self.lib_dir])
    return link_cmd

  def _get_hierarchy(self, file_to_build):
    """
    Create a hierarchy of compiling commands accordingly to the dependencies order.

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

  def _compile(self, file_to_build, verbose=False, log=False, quiet=False):
    """
    Compile file.

    Parameters
    ----------
    file_to_build : ParsedFile
    verbose : {False}
      bool for activate extreme verbose outputs
    log : {False}
      bool for activate errors log saving

    Returns
    -------
    build_ok : bool
      flag for checking the building is completed;
      it is used for purging out failed non-module-library in order to try to build the target anywhere;
    """
    build_ok = True
    hierarchy = self._get_hierarchy(file_to_build)
    for deps in reversed(hierarchy):
      files_to_compile = ''
      cmds = []
      for dep in deps:
        files_to_compile = files_to_compile + " " + dep[0]
        cmds.append(dep[1])
      if len(deps) > 1 and self.jobs > 1 and __parallel__:
        jobs = min(len(deps), self.jobs)
        if not quiet:
          self.print_n("Compiling" + files_to_compile + " using " + str(jobs) + " concurrent processes")
          if verbose:
            self.print_n("Executing: " + str(cmds))
        pool = Pool(processes=jobs)
        results = pool.map(syswork, cmds)
        pool.close()
        pool.join()
      else:
        if not quiet:
          self.print_n("Compiling" + files_to_compile + " serially")
        results = []
        for cmd in cmds:
          if not quiet:
            if verbose:
              self.print_n("Executing: " + str(cmd))
          result = syswork(cmd)
          results.append(result)
      if not file_to_build.nomodlib:
        if log:
          check_results(results=results, log="building-errors.log", print_w=self.print_w)
        else:
          check_results(results=results, print_w=self.print_w)
    if file_to_build.nomodlib:
      if results[0][0] != 0:
        build_ok = False
        if not quiet:
          self.print_w('Warning: compiling file ' + file_to_build.name + ' fails! Removing from the list of non-module libraries linked into the target!')
    return build_ok

  def gnu_make(self):
    """
    Return the builder options formated as GNU Make variables

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

  def build(self, file_to_build, output=None, nomodlibs=None, submodules=None, mklib=None, verbose=False, log=False, quiet=False, track=False):
    """
    Build a file.

    Parameters
    ----------
    file_to_build : ParsedFile
    output : str
      output name
    nomodlibs : {None}
      list of old-Fortran style libraries objects
    submodules : {None}
      list of submodules objects
    mklib : {None}
      bool for activate building library mode
    verbose : {False}
      bool for activate extreme verbose outputs
    log : {False}
      bool for activate errors log saving
    quiet : {False}
      bool for activate quiet mode
    track : {False}
      bool for activate build traking mode for subsequent install command

    Returns
    -------
    build_ok : bool
      flag for checking the building is completed;
      it is used for purging out failed non-module-library in order to try to build the target anywhere;
    """
    build_ok = True
    if not quiet:
      self.print_n('Building ' + file_to_build.name)
    # sort dependencies accordingly to indirect dependency
    file_to_build.sort_dependencies()
    # creating a hierarchy list of compiling commands accordingly to the order of all dependencies
    if len([p for p in file_to_build.pfile_dep_all if not p.include and p.to_compile]) > 0:
      build_ok = self._compile(file_to_build=file_to_build, verbose=verbose, log=log, quiet=quiet)
    else:
      if not quiet:
        self.print_n('Nothing to compile, all objects are up-to-date')
    if file_to_build.program:
      link_cmd, exe = self._link_command(file_to_build=file_to_build, output=output, nomodlibs=nomodlibs, submodules=submodules, mklib=mklib)
      if not quiet:
        self.print_n("Linking " + exe)
        if verbose:
          self.print_n("Executing: " + str(link_cmd))
      result = syswork(link_cmd)
      if log:
        check_results(results=[result], log="building-errors.log", print_w=self.print_w)
      else:
        check_results(results=[result], print_w=self.print_w)
      if not quiet:
        self.print_n('Target ' + file_to_build.name + ' has been successfully built')
    elif mklib:
      link_cmd, lib = self._mklib_command(file_to_build=file_to_build, output=output, nomodlibs=nomodlibs, submodules=submodules, mklib=mklib)
      if not quiet:
        self.print_n("Linking " + lib)
        if verbose:
          self.print_n("Executing: " + str(link_cmd))
      result = syswork(link_cmd)
      if log:
        check_results(results=[result], log="building-errors.log", print_w=self.print_w)
      else:
        check_results(results=[result], print_w=self.print_w)
      if not quiet:
        self.print_n('Target ' + file_to_build.name + ' has been successfully built')
    if track:
      print('Track building of ' + file_to_build.name)
      track_file_name = self.get_track_build_file(file_to_build)
      with open(track_file_name, 'w') as track_file:
        track_file.writelines('[build]\n')
        track_file.writelines('output = ' + self.get_output_name(file_to_build=file_to_build, output=output) + '\n')
        if file_to_build.program:
          track_file.writelines('program = True\n')
        elif mklib:
          track_file.writelines('library = True\n')
          track_file.writelines('mod_file = ' + os.path.join(self.mod_dir, file_to_build.basename + '.mod') + '\n')
    return build_ok

  def get_output_name(self, file_to_build, output=None, mklib=None):
    """
    Return the output build file name.

    Parameters
    ----------
    file_to_build : ParsedFile
    output : str
      output build file name
    mklib : {None}
      activate building library mode

    Returns
    -------
    output : str
      output build file name
    """
    if output:
      build_name = os.path.join(self.build_dir, output)
    else:
      if mklib is not None:
        if mklib.lower() == 'shared':
          build_name = os.path.join(self.build_dir, file_to_build.basename + '.so')
        elif mklib.lower() == 'static':
          build_name = os.path.join(self.build_dir, file_to_build.basename + '.a')
      else:
        build_name = os.path.join(self.build_dir, file_to_build.basename)
    return build_name

  def get_track_build_file(self, file_to_build):
    """
    Return the file name of the 'track build' file.

    Parameters
    ----------
    file_to_build : ParsedFile

    Returns
    -------
    track_file_name : str
      file name of 'track build' file
    """
    return os.path.join(self.build_dir, '.' + os.path.basename(file_to_build.name) + '.track_build')

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
      message += "  Preprocessor used: " + str(self.preprocessor) + "\n"
      message += "  Preprocessor output directory: " + str(self.preprocessor_dir) + "\n"
      message += "  Preprocessor extensions processed: " + str(self.preprocessor_ext) + "\n"
    return message
