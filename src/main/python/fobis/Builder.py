#!/usr/bin/env python
"""
Builder.py, module definition of Builder class.
This is a class designed for controlling the building phase.
"""
try:
  from multiprocessing import Pool
  __parallel__ = True
except ImportError:
  print("Module 'multiprocessing' not found: parallel compilation disabled")
  __parallel__ = False
import operator
import os
import sys
from .Colors import Colors
from .utils import syswork


class Builder(object):
  """Builder is an object that handles the building system, its attributes and methods."""
  def __init__(self,
               compiler="Intel",
               fc="",
               modsw="",
               mpi=False,
               cflags="",
               lflags="",
               libs=None,
               ext_libs=None,
               dinc=None,
               preproc="",
               build_dir="./",
               mod_dir="./",
               lib_dir=None,
               obj_dir="./",
               quiet=False,
               colors=False,
               jobs=1,
               preform=False,
               pfm_dir=None,
               pfm_ext=None):
    """
    Parameters
    ----------
    compiler : {"Intel"}
      compiler used
    fc : {""}
      custom compiler statement
    modsw : {""}
      custom compiler switch for modules searching path
    mpi : {False}
      use MPI enabled version of compiler
    cflags : {""}
      compilation flags
    lflags : {""}
      linking flags
    libs : {None}
      list of external libraries that are not into the path: must be passed with full paths
    ext_libs : {None}
      list of external libraries that are into the path: are linked as '-llibrary.[a|so]' and searched into '-Ldir'
    dinc : {None}
      list of directories for searching included files
    preproc : {""}
      preprocessor flags
    build_dir : {"./"}
      directory containing built files
    mod_dir : {"./"}
      directory containing .mod files
    lib_dir : {None}
      list of directories searched for libraries
    obj_dir : {"./"}
      directory containing compiled object files
    quiet : {False}
      make printings less verbose than default
    colors : {False}
      make printings colored
    jobs : {1}
      concurrent compiling jobs
    preform : {False}
      activate PreForM.py pre-processing
    pfm_dir : {None}
      directory containing sources processed by PreForm.py; by default are removed after used
    pfm_ext : {None}
      list of file extensions to be processed by PreForm.py; by default all files are preprocessed if PreForM.py is used

    Attributes
    ----------
    """
    self.compiler = compiler
    self.fcs = fc
    self.modsw = modsw
    self.mpi = mpi
    self.cflags = cflags
    self.lflags = lflags
    if libs is None:
      self.libs = []
    else:
      self.libs = libs
    if ext_libs is None:
      self.ext_libs = []
    else:
      self.ext_libs = ext_libs
    if dinc is None:
      self.dinc = []
    else:
      self.dinc = dinc
    self.preproc = preproc
    self.build_dir = build_dir
    self.mod_dir = build_dir + mod_dir
    self.obj_dir = build_dir + obj_dir
    if lib_dir is None:
      self.lib_dir = []
    else:
      self.lib_dir = lib_dir
    self.quiet = quiet
    self.colors = Colors()
    self.jobs = jobs
    self.preform = preform
    if pfm_ext is None:
      self.pfm_ext = []
    else:
      self.pfm_ext = pfm_ext
    self.pfm_dir = pfm_dir
    if self.pfm_dir:
      self.pfm_dir = build_dir + self.pfm_dir
    if not colors:
      self.colors.disable()
    if self.preform:
      pfm_exist = False
      for path in os.environ["PATH"].split(os.pathsep):
        pfm_exist = os.path.exists(os.path.join(path, 'PreForM.py'))
        if pfm_exist:
          if self.pfm_dir:
            if not os.path.exists(self.pfm_dir):
              os.makedirs(self.pfm_dir)
          break
      if not pfm_exist:
        print(self.colors.red + 'Error: PreForM.py is not in your PATH! You cannot use --preform or -pfm switches.' + self.colors.end)
        sys.exit(1)
    if mpi:
      self.fcs = 'mpif90'
    if compiler.lower() == 'gnu':
      if not mpi:
        self.fcs = 'gfortran'
      self.modsw = '-J'
    elif compiler.lower() == 'intel':
      if not mpi:
        self.fcs = 'ifort'
      self.modsw = '-module'
    elif compiler.lower() == 'g95':
      if not mpi:
        self.fcs = 'g95'
      self.modsw = '-fmod='
    elif compiler.lower() == 'custom':
      pass  # all is set from CLI
    if self.modsw[-1] != '=':  # check necessary for g95 CLI trapping error
      self.modsw += ' '
    self.cmd_comp = self.fcs + ' ' + self.cflags + ' ' + self.modsw + self.mod_dir + ' ' + self.preproc
    self.cmd_link = self.fcs + ' ' + self.lflags + ' ' + self.modsw + self.mod_dir
    # checking paths integrity
    if not os.path.exists(self.mod_dir):
      os.makedirs(self.mod_dir)
    if not os.path.exists(self.obj_dir):
      os.makedirs(self.obj_dir)
    if not os.path.exists(self.build_dir):
      os.makedirs(self.build_dir)

  def __compile_preform(self, file_to_compile):
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
        preform_cmd = 'PreForM.py ' + file_to_compile.name + ' -o ' + pfm_dir + file_to_compile.basename + '.pfm.f90' + ' ; '
        preform_output = pfm_dir + file_to_compile.basename + '.pfm.f90'
        if not preform_store:
          preform_remove = ' ; rm -f ' + preform_output
    return preform_cmd, preform_output, preform_remove

  def __compile_include(self):
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

  def compile_command(self, file_to_compile):
    """
    The method compile_command returns the OS command for compiling file_to_compile.

    Parameters
    ----------
    file_to_compile : ParsedFile object
      file to be compiled

    Returns
    -------
    str
      string containing the compile command
    """
    preform_cmd, preform_output, preform_remove = self.__compile_preform(file_to_compile)
    include_cmd = self.__compile_include()

    if preform_cmd != '':
      comp_cmd = preform_cmd + self.cmd_comp + include_cmd + preform_output + ' -o ' + self.obj_dir + file_to_compile.basename + '.o' + preform_remove
    else:
      comp_cmd = self.cmd_comp + include_cmd + file_to_compile.name + ' -o ' + self.obj_dir + file_to_compile.basename + '.o'
    return comp_cmd

  def build(self, file_to_build, output=None, nomodlibs=None, mklib=None):
    """
    Method for building file.

    Parameters
    ----------
    file_to_build : ParsedFile
    output :
    nomodlibs : {None}
      list of old-Fortran style libraries objects
    mklib : {None}
    """
    print(self.colors.bld + 'Building ' + file_to_build.name + self.colors.end)
    # correct the list ordering accordingly to indirect dependency
    for dep in file_to_build.pfile_dep_all:
      for other_dep in file_to_build.pfile_dep_all:
        if other_dep != dep:
          if dep in other_dep.pfile_dep_all:
            dep.order += 1
    file_to_build.pfile_dep_all.sort(key=operator.attrgetter('order'), reverse=True)
    # creating a hierarchy list of compiling commands accordingly to the order of all dependencies
    if len([p for p in file_to_build.pfile_dep_all if not p.include and p.to_compile]) > 0:
      order_max = max([p for p in file_to_build.pfile_dep_all if not p.include and p.to_compile], key=operator.attrgetter('order')).order + 1
      hierarchy = [[] for i in range(order_max)]
      for dep in file_to_build.pfile_dep_all:
        if dep.to_compile and not dep.include:
          hierarchy[dep.order].append([dep.name, self.compile_command(file_to_compile=dep)])
          dep.to_compile = False
      hierarchy = [h for h in hierarchy if len(h) > 0]
      for deps in reversed(hierarchy):
        files_to_compile = ''
        cmds = []
        for dep in deps:
          files_to_compile = files_to_compile + " " + dep[0]
          cmds.append(dep[1])
        if len(deps) > 1 and self.jobs > 1 and __parallel__:
          jobs = min(len(deps), self.jobs)
          print(self.colors.bld + "Compiling" + files_to_compile + " using " + str(jobs) + " concurrent processes" + self.colors.end)
          pool = Pool(processes=jobs)
          results = pool.map(syswork, cmds)
          pool.close()
          pool.join()
          if not all(v[0] == 0 for v in results):
            for result in results:
              if result[0] != 0:
                print(self.colors.red + result[1] + self.colors.end)
            sys.exit(1)
          if not all(v[1] == '' for v in results):
            for result in results:
              if result[1] != '':
                print(self.colors.red + result[1] + self.colors.end)
        else:
          print(self.colors.bld + "Compiling" + files_to_compile + " serially " + self.colors.end)
          for cmd in cmds:
            result = syswork(cmd)
            if result[0] != 0:
              print(self.colors.red + result[1] + self.colors.end)
              sys.exit(1)
    else:
      print(self.colors.bld + 'Nothing to compile, all objects are up-to-date' + self.colors.end)
    if file_to_build.program:
      if nomodlibs is not None:
        objs = nomodlibs + file_to_build.obj_dependencies()
      else:
        objs = file_to_build.obj_dependencies()
      if output:
        exe = self.build_dir + output
      else:
        exe = self.build_dir + file_to_build.basename
      link_cmd = self.cmd_link + " " + "".join([self.obj_dir + s + " " for s in objs]) + "".join([s + " " for s in self.libs])
      if len(self.ext_libs) > 0:
        link_cmd += " " + "".join(["-l" + s + " " for s in self.ext_libs])
      if len(self.lib_dir) > 0:
        link_cmd += " " + "".join(["-L" + s + " " for s in self.lib_dir])
      link_cmd += " -o " + exe
      print(self.colors.bld + "Linking " + exe + self.colors.end)
      result = syswork(link_cmd)
      if result[0] != 0:
        print(self.colors.red + result[1] + self.colors.end)
        sys.exit(1)
      print(self.colors.bld + 'Target ' + file_to_build.name + ' has been successfully built' + self.colors.end)
    elif mklib:
      if output:
        lib = self.build_dir + output
      else:
        if mklib.lower() == 'shared':
          lib = self.build_dir + file_to_build.basename + '.so'
        elif mklib.lower() == 'static':
          lib = self.build_dir + file_to_build.basename + '.a'
      if mklib.lower() == 'shared':
        link_cmd = self.cmd_link + " " + "".join([s + " " for s in self.libs]) + self.obj_dir + file_to_build.basename + ".o -o " + lib
      elif mklib.lower() == 'static':
        link_cmd = "ar -rcs " + lib + " " + self.obj_dir + file_to_build.basename + ".o ; ranlib " + lib
      print(self.colors.bld + "Linking " + lib + self.colors.end)
      result = syswork(link_cmd)
      if result[0] != 0:
        print(self.colors.red + result[1] + self.colors.end)
        sys.exit(1)
      print(self.colors.bld + 'Target ' + file_to_build.name + ' has been successfully built' + self.colors.end)

  def verbose(self):
    """
    The method verbose returns a verbose message containing builder infos.
    """
    message = ''
    if not self.quiet:
      message = "Builder options" + "\n"
      message += "  Compiled-objects .o   directory: " + self.obj_dir + "\n"
      message += "  Compiled-objects .mod directory: " + self.mod_dir + "\n"
      if len(self.lib_dir) > 0:
        message += "  External libraries directories:  " + "".join([s + " " for s in self.lib_dir]) + "\n"
      else:
        message += "  External libraries directories:  " + str(self.lib_dir) + "\n"
      message += "  Building directory:              " + self.build_dir + "\n"
      if len(self.dinc) > 0:
        message += "  Included paths:                  " + "".join([s + " " for s in self.dinc]) + "\n"
      else:
        message += "  Included paths:                  " + str(self.dinc) + "\n"
      if len(self.libs) > 0:
        message += "  Linked libraries with full path: " + "".join([s + " " for s in self.libs]) + "\n"
      else:
        message += "  Linked libraries with full path: " + str(self.libs) + "\n"
      if len(self.ext_libs) > 0:
        message += "  Linked libraries in path:        " + "".join([s + " " for s in self.ext_libs]) + "\n"
      else:
        message += "  Linked libraries in path:        " + str(self.ext_libs) + "\n"
      message += "  Compiler class:                  " + self.compiler + "\n"
      message += "  Compiler:                        " + self.fcs + "\n"
      message += "  Compiler module switch:          " + self.modsw + "\n"
      message += "  Compilation flags:               " + self.cflags + "\n"
      message += "  Linking     flags:               " + self.lflags + "\n"
      message += "  Preprocessing flags:             " + self.preproc + "\n"
      message += "  PreForM.py used:                 " + str(self.preform) + "\n"
      message += "  PreForM.py output directory:     " + str(self.pfm_dir) + "\n"
      message += "  PreForM.py extensions processed: " + str(self.pfm_ext) + "\n"
    return message
