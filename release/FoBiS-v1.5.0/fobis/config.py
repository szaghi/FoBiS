#!/usr/bin/env python
"""
config.py, module definition of FoBiS.py configuration.
"""
import hashlib
import os
import sys
from .CliParser import CliParser
from .Colors import Colors
from .utils import syswork
__appname__ = "FoBiS.py"
__version__ = "v1.5.0"
__author__ = "Stefano Zaghi"
__author_email__ = "stefano.zaghi@gmail.com"
__license__ = "GNU General Public License v3 (GPLv3)"
__url__ = "https://github.com/szaghi/FoBiS"
__description__ = "a Fortran Building System for poor men"
__long_description__ = "FoBiS.py, a Fortran Building System for poor men, is a KISS tool for automatic building modern Fortran projects, it being able to automatically resolve inter-modules dependancy hierarchy."


class FoBiSConfig(object):
  """
  Object handling FoBiS.py configuration
  """
  def __init__(self):
    """
    Attributes
    ----------
    quiet : {False}
      less verbose printing messages
    colors : {Colors}
      Colors object
    extensions_inc : {[".inc", ".INC", ".h", ".H"]}
      list of extensions of included files
    extensions_old : {[".f", ".F", ".for", ".FOR", ".fpp", ".FPP", ".fortran", ".f77", ".F77"]}
      list of extensions of old Fortran format parsed
    extensions_modern : {[".f90", ".F90", ".f95", ".F95", ".f03", ".F03", ".f08", ".F08", ".f2k", ".F2K"]}
      list of extensions of modern Fortran format parsed
    extensions_parsed : {extensions_old + extensions_modern}
      list of extensions of Fortran format parsed
    cliargs : {None}
      CLI arguments, argparse object
    force_compile : {False}
      flag for forcing (re-)compiling all
    """
    self.quiet = False
    self.colors = Colors()
    self.extensions_inc = [".inc", ".INC", ".h", ".H"]
    self.extensions_old = [".f", ".F", ".for", ".FOR", ".fpp", ".FPP", ".fortran", ".f77", ".F77"]
    self.extensions_modern = [".f90", ".F90", ".f95", ".F95", ".f03", ".F03", ".f08", ".F08", ".f2k", ".F2K"]
    self.extensions_parsed = self.extensions_old + self.extensions_modern
    self.cliargs = None
    self.force_compile = False
    return

  def __str__(self):
    string = ['FoBiS.py configuration']
    string.append('\n  Quiet mode: ' + str(self.quiet))
    string.append('\n  Extensions of included files: ' + str(self.extensions_inc))
    string.append('\n  Extensions of parsed files:   ' + str(self.extensions_parsed))
    return ''.join(string)

  def reset(self):
    """
    Method for restoring default (init) values.
    """
    self.__init__()
    return

  def printf(self):
    """Method for printing config data. It checks verbosity."""
    if not self.quiet:
      print(self)
    return

  def get_cli(self, fake_args=None):
    """
    Method for parsing CLI arguments.

    Parameters
    ----------
    fake_args : {None}
      list containing fake CLAs for using without CLI
    """
    cliparser = CliParser(appname=__appname__, description='FoBiS.py, Fortran Building System for poor men', version=__version__)
    if fake_args:
      self.cliargs = cliparser.parse_args(fake_args)
    else:
      self.cliargs = cliparser.parse_args()
    if not self.cliargs.colors:
      self.colors.disable()
    if self.cliargs.which == 'clean' or self.cliargs.which == 'build':
      self.cliargs.build_dir = os.path.normpath(self.cliargs.build_dir) + "/"
      self.cliargs.mod_dir = os.path.normpath(self.cliargs.mod_dir) + "/"
      self.cliargs.obj_dir = os.path.normpath(self.cliargs.obj_dir) + "/"
    if self.cliargs.which == 'build':
      self.cliargs.src = os.path.normpath(self.cliargs.src) + "/"
    return

  def update_extensions(self):
    """Method for updating files extensions"""
    if self.cliargs.which == 'build':
      self.extensions_inc += self.cliargs.inc
    self.extensions_parsed += self.extensions_inc
    if self.cliargs.which == 'build':
      if len(self.cliargs.pfm_ext) > 0:
        self.extensions_parsed += self.cliargs.pfm_ext
    return

  def check_cflags_heritage(self):
    """
    Method for checking the heritage of cflags: if a file named '.cflags.heritage' is found into the root dir FoBiS.py is runned that file
    is sourced and compared with the actual cflags and in case they differ the project is forced to be recompiled. The actual cflags are saved,
    in any case, into that file.
    """
    if self.cliargs.which == 'build':
      if self.cliargs.cflags_heritage:
        if os.path.exists(self.cliargs.build_dir + '.cflags.heritage'):
          cflags_old = open(self.cliargs.build_dir + '.cflags.heritage').read()
          if self.cliargs.cflags != cflags_old:
            self.force_compile = True
            print(self.colors.red + "The present cflags are different from the heritages one: forcing to (re-)compile all" + self.colors.end)
        with open(self.cliargs.build_dir + '.cflags.heritage', 'w') as chf:
          chf.writelines(self.cliargs.cflags)
    return

  @staticmethod
  def check_md5sum(filename, hashfile):
    """
    Function for checking the md5sum hash of a file, compares with an eventual hashfile into which the hash is finally saved.

    Parameters
    ----------
    filename : str
      file name (with path) of file to be hashed
    hashfile : str
      file eventually present containing the hash and into which the hash is finally saved

    Returns
    -------
    2 bools containing the previously existance of the hashfile and the result of hashes comparison
    """
    md5sum = hashlib.md5(open(filename, 'rb').read()).hexdigest()
    hashexist = os.path.exists(hashfile)
    comparison = False
    if hashexist:
      md5sum_old = open(hashfile).read()
      comparison = md5sum == md5sum_old
    with open(hashfile, 'w') as md5:
      md5.writelines(md5sum)
    return hashexist, comparison

  def check_vlibs_md5sum(self):
    """
    Method for checking if the md5sum of volatile libraries has changed and, in case, a re-build is triggered.
    """
    if self.cliargs.which == 'build':
      if len(self.cliargs.vlibs) > 0:
        for lib in self.cliargs.vlibs:
          if not os.path.exists(lib):
            print(self.colors.red + "The volatile library " + lib + " is not found!" + self.colors.end)
            sys.exit(1)
          hashfile, comparison = self.check_md5sum(filename=lib, hashfile=self.cliargs.build_dir + '.' + os.path.basename(lib) + '.md5')
          if hashfile:
            self.force_compile = not comparison
            if self.force_compile:
              print(self.colors.red + "The volatile library " + lib + " is changed with respect the last building: forcing to (re-)compile all" + self.colors.end)
    return

  def check_ext_vlibs_md5sum(self):
    """
    Method for checking if the md5sum of volatile external libraries has changed and, in case, a re-build is triggered.
    """
    if self.cliargs.which == 'build':
      if len(self.cliargs.ext_vlibs) > 0:
        for lib in self.cliargs.ext_vlibs:
          lib_found = False
          if len(self.cliargs.lib_dir) > 0:
            for dirp in self.cliargs.lib_dir:
              libpath = os.path.join(dirp, 'lib' + lib + '.a')
              lib_found = os.path.exists(libpath)
              if lib_found:
                break
              libpath = os.path.join(dirp, 'lib' + lib + '.so')
              lib_found = os.path.exists(libpath)
              if lib_found:
                break
          else:
            libpath = 'lib' + lib + '.a'
            lib_found = os.path.exists(libpath)
            if not lib_found:
              libpath = 'lib' + lib + '.so'
              lib_found = os.path.exists(libpath)
          if not lib_found:
            print(self.colors.red + "The volatile library " + lib + " is not found!" + self.colors.end)
            sys.exit(1)
          hashfile, comparison = self.check_md5sum(filename=libpath, hashfile=self.cliargs.build_dir + '.' + os.path.basename(libpath) + '.md5')
          if hashfile:
            self.force_compile = not comparison
            if self.force_compile:
              print(self.colors.red + "The volatile library " + lib + " is changed with respect the last building: forcing to (re-)compile all" + self.colors.end)
    return

  def check_interdependent_fobos(self):
    """
    Method for checking interdependency project by its fobos.
    """
    if self.cliargs.which == 'build':
      if self.cliargs.dependon:
        fobos_path = os.path.dirname(self.cliargs.dependon)
        fobos_file = os.path.basename(self.cliargs.dependon)
        mode = ''
        if ":" in fobos_file:
          fobos_file = os.path.basename(self.cliargs.dependon).split(":")[0]
          mode = os.path.basename(self.cliargs.dependon).split(":")[1]
        if mode != '':
          print(self.colors.bld + "Building dependency " + fobos_file + " into " + fobos_path + " with mode " + mode + self.colors.end)
          old_pwd = os.getcwd()
          os.chdir(old_pwd + '/' + fobos_path)
          result = syswork("FoBiS.py build -f " + fobos_file + " -mode " + mode)
          print(result[1])
          os.chdir(old_pwd)
          if result[0] != 0:
            sys.exit(result[0])
        else:
          print(self.colors.bld + "Building dependency " + fobos_file + " into " + fobos_path + " with default mode" + self.colors.end)
          old_pwd = os.getcwd()
          os.chdir(old_pwd + '/' + fobos_path)
          result = syswork("FoBiS.py build -f " + fobos_file)
          print(result[1])
          os.chdir(old_pwd)
          if result[0] != 0:
            sys.exit(result[0])
    return

# global variables
__initialized__ = False
if not __initialized__:
  __config__ = FoBiSConfig()
  __initialized__ = True
