#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FoBiSConfig.py, module definition of FoBiS.py configuration.
"""
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals
# Copyright (C) 2020  Stefano Zaghi
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
from future import standard_library
standard_library.install_aliases()
from builtins import str
from builtins import *
from builtins import object
import hashlib
import os
import re
import sys
from .Builder import Builder
from .Colors import Colors
from .Fobos import Fobos
from .cli_parser import cli_parser
from .utils import syswork

__appname__ = "FoBiS.py"
__version__ = "3.0.6"
__author__ = "Stefano Zaghi"
__author_email__ = "stefano.zaghi@gmail.com"
__license__ = "GNU General Public License v3 (GPLv3)"
__url__ = "https://github.com/szaghi/FoBiS"
__description__ = "a Fortran Building System for poor men"
__long_description__ = "FoBiS.py, a Fortran Building System for poor men, is a KISS tool for automatic building modern Fortran projects, it being able to automatically resolve inter-modules dependancy hierarchy."


class FoBiSConfig(object):
  """
  FoBiS configuration class handling.
  """
  def __init__(self, fake_args=None):
    """
    Attributes
    ----------
    cliargs : argparse.ArgumentParser()
      CLI arguments, argparse object
    fobos : Fobos()
      Fobos object, the FoBiS.py makefile
    colors : {Colors()}
      Colors object
    """
    cliparser = cli_parser(appname=__appname__, description=__description__, version=__version__)
    self.cliargs = cliparser.parse_args(fake_args)
    self.colors = Colors()
    self.fobos = Fobos(cliargs=self.cliargs, print_n=self.print_b, print_w=self.print_r)
    self.colors = Colors(enabled=self.cliargs.colors)  # reset colors accordingly fobos options
    self._postinit()

  def _update_extensions(self):
    """Update files extensions"""
    if self.cliargs.which == 'build' or self.cliargs.which == 'rule':
      for inc in self.cliargs.inc:
        if inc not in self.cliargs.extensions:
          self.cliargs.extensions.append(inc)
      if len(self.cliargs.preprocessor_ext) > 0:
        self.cliargs.extensions += self.cliargs.preprocessor_ext

  def _sanitize_paths(self):
    """
    Sanitize paths.
    """
    if self.cliargs.which == 'clean' or self.cliargs.which == 'build' or self.cliargs.which == 'rule':
      self.cliargs.build_dir = os.path.normpath(self.cliargs.build_dir)
      self.cliargs.mod_dir = os.path.normpath(self.cliargs.mod_dir)
      self.cliargs.obj_dir = os.path.normpath(self.cliargs.obj_dir)
    if self.cliargs.which == 'build' or self.cliargs.which == 'rule':
      for n, src in enumerate(self.cliargs.src):
        self.cliargs.src[n] = os.path.normpath(src)
      for n, inc in enumerate(self.cliargs.include):
        self.cliargs.include[n] = os.path.normpath(inc)
      for n, exc in enumerate(self.cliargs.exclude_dirs):
        self.cliargs.exclude_dirs[n] = os.path.normpath(exc)
    if self.cliargs.which == 'install':
      self.cliargs.build_dir = os.path.normpath(self.cliargs.build_dir)
      self.cliargs.prefix = os.path.normpath(self.cliargs.prefix)
      self.cliargs.bin = os.path.normpath(self.cliargs.bin)
      self.cliargs.lib = os.path.normpath(self.cliargs.lib)
      self.cliargs.include = os.path.normpath(self.cliargs.include)

  def _check_cflags_heritage(self):
    """
    Check the heritage of cflags: if a file named '.cflags.heritage' is found into the root dir FoBiS.py is runned that file
    is sourced and compared with the actual cflags and in case they differ the project is forced to be recompiled. The actual cflags are saved,
    in any case, into that file.
    """
    if self.cliargs.which == 'build' or self.cliargs.which == 'rule':
      if self.cliargs.cflags_heritage:
        cflags = Builder.get_cflags(cliargs=self.cliargs)
        if self.cliargs.target:
          her_file = os.path.join(self.cliargs.build_dir, '.' + os.path.basename(self.cliargs.target) + '.cflags.heritage')
        else:
          her_file = os.path.join(self.cliargs.build_dir, '.cflags.heritage')
        if os.path.exists(her_file):
          cflags_old = open(her_file).read()
          if cflags != cflags_old:
            self.cliargs.force_compile = True
            self.print_r("The present cflags are different from the heritages one: forcing to (re-)compile all")
        if not os.path.exists(self.cliargs.build_dir):
          os.makedirs(self.cliargs.build_dir)
        with open(her_file, 'w') as chf:
          chf.writelines(cflags)

  def _postinit(self):
    """
    Post-initialization update of config attributes, after CLI and fobos parsing.
    """
    self._update_extensions()
    self._sanitize_paths()
    self._check_cflags_heritage()
    if self.cliargs.which == 'build' or self.cliargs.which == 'rule':
      if len(self.cliargs.vlibs) > 0:
        self._check_vlibs_md5sum()
      if len(self.cliargs.ext_vlibs) > 0:
        self._check_ext_vlibs_md5sum()
    self._check_interdependent_fobos()

  @staticmethod
  def _check_md5sum(filename, hashfile):
    """
    Check the md5sum hash of a file, compares with an eventual hashfile into which the hash is finally saved.

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

  def _check_vlibs_md5sum(self):
    """
    Check if the md5sum of volatile libraries has changed and, in case, a re-build is triggered.
    """
    for lib in self.cliargs.vlibs:
      if not os.path.exists(lib):
        self.print_r("The volatile library " + lib + " is not found!")
      hashfile, comparison = self._check_md5sum(filename=lib, hashfile=os.path.join(self.cliargs.build_dir, '.' + os.path.basename(lib) + '.md5'))
      if hashfile:
        self.cliargs.force_compile = (not comparison) or self.cliargs.force_compile
        if not comparison:
          self.print_r("The volatile library " + lib + " is changed with respect the last building: forcing to (re-)compile all")

  def _check_ext_vlibs_md5sum(self):
    """
    Check if the md5sum of volatile external libraries has changed and, in case, a re-build is triggered.
    """
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
        self.print_r("The volatile library " + lib + " is not found!")
      hashfile, comparison = self._check_md5sum(filename=libpath, hashfile=os.path.join(self.cliargs.build_dir, '.' + os.path.basename(libpath) + '.md5'))
      if hashfile:
        self.cliargs.force_compile = (not comparison) or self.cliargs.force_compile
        if not comparison:
          self.print_r("The volatile library " + lib + " is changed with respect the last building: forcing to (re-)compile all")

  def _add_include_paths(self, add_paths):
    """
    Add include files search paths.

    Parameters
    ----------
    add_paths : list
      added paths, each element has 3 elements: path[0] libraries search path, path[1] include files search path, path[2] the library
    """
    self.print_r("Include files search paths (include):")
    for path in add_paths:
      if self.cliargs.include:
        self.cliargs.include.append(path[1])
      else:
        self.cliargs.include = [path[1]]
      self.print_r("- " + path[1])

  def _add_lib_dir_paths(self, add_paths):
    """
    Add libraries search paths.

    Parameters
    ----------
    add_paths : list
      added paths, each element has 3 elements: path[0] libraries search path, path[1] include files search path, path[2] the library
    """
    self.print_r("Libraries search paths (lib_dir):")
    for path in add_paths:
      if path[2][1].lower() == 'indirect':
        if self.cliargs.lib_dir:
          self.cliargs.lib_dir.append(path[0])
        else:
          self.cliargs.lib_dir = [path[0]]
        self.print_r("- " + path[0])

  def _add_ext_libs_paths(self, add_paths):
    """
    Add libraries paths.

    Parameters
    ----------
    add_paths : list
      added paths, each element has 3 elements: path[0] libraries search path, path[1] include files search path, path[2] the library
    """
    self.print_r("Libraries paths:")
    for path in add_paths:
      if path[2][1].lower() == 'indirect':
        lib = re.sub(r"^lib", '', os.path.basename(path[2][0]))
        lib = re.sub(r"\.a$", '', lib)
        lib = re.sub(r"\.so$", '', lib)
        if self.cliargs.ext_libs:
          self.cliargs.ext_libs.append(lib)
        else:
          self.cliargs.ext_libs = [lib]
        self.print_r("- (ext_libs) " + lib)
      else:
        if self.cliargs.libs:
          self.cliargs.libs.append(path[2][0])
        else:
          self.cliargs.libs = [path[2][0]]
        self.print_r("- (libs) " + path[2][0])

  def _add_auxiliary_paths(self, add_paths):
    """
    Add auxiliary paths to default searched ones.

    Parameters
    ----------
    add_paths : list
      added paths, each element has 3 elements: path[0] libraries search path, path[1] include files search path, path[2] the library
    """
    self.print_r("The following auxiliary paths have been added")
    self._add_include_paths(add_paths=add_paths)
    self._add_lib_dir_paths(add_paths=add_paths)
    self._add_ext_libs_paths(add_paths=add_paths)

  def _check_interdependent_fobos(self):
    """
    Check interdependency project by its fobos.
    """
    if self.cliargs.which == 'build' and not self.cliargs.lmodes:
      if len(self.cliargs.dependon) > 0:
        add_paths = []
        for dependon in self.cliargs.dependon:
          fobos_path = os.path.dirname(dependon)
          fobos_file = os.path.basename(dependon)
          mode = ''
          linking = ''
          matching = re.match(r"^.*\(\((?P<link>.*)\)\).*$", fobos_file)
          if matching:
            linking = matching.group('link')
            fobos_file = re.sub(r"\(\(.*\)\)", '', fobos_file)
          if ":" in fobos_file:
            mode = os.path.basename(fobos_file).split(":")[1]
            fobos_file = os.path.basename(fobos_file).split(":")[0]
          old_pwd = os.getcwd()
          os.chdir(os.path.join(old_pwd, fobos_path))
          if mode != '':
            self.print_b("Building dependency " + fobos_file + " into " + fobos_path + " with mode " + mode)
            result = syswork("FoBiS.py build -f " + fobos_file + " -mode " + mode)
            dbld = syswork("FoBiS.py rule -f " + fobos_file + " -mode " + mode + " -get build_dir")
            dmod = syswork("FoBiS.py rule -f " + fobos_file + " -mode " + mode + " -get mod_dir")
            output = syswork("FoBiS.py rule -f " + fobos_file + " -mode " + mode + " -get_output_name")
          else:
            self.print_b("Building dependency " + fobos_file + " into " + fobos_path + " with default mode")
            result = syswork("FoBiS.py build -f " + fobos_file)
            dbld = syswork("FoBiS.py rule -f " + fobos_file + " -get build_dir")
            dmod = syswork("FoBiS.py rule -f " + fobos_file + " -get mod_dir")
            output = syswork("FoBiS.py rule -f " + fobos_file + " -get_output_name")
          os.chdir(old_pwd)
          print(result[1])
          if result[0] != 0:
            sys.exit(result[0])
          add_paths.append([os.path.normpath(os.path.join(fobos_path, dbld[1].strip('\n'))),
                            os.path.normpath(os.path.join(fobos_path, dbld[1].strip('\n'), dmod[1].strip('\n'))),
                            [os.path.normpath(os.path.join(fobos_path, output[1].strip('\n'))), linking]])
        self._add_auxiliary_paths(add_paths)

  def print_b(self, string, end='\n'):
    """
    Print string with bold color.

    Parameters
    ----------
    string : str
      string to be printed
    """
    self.colors.print_b(string, end=end)

  def print_r(self, string, end='\n'):
    """
    Print string with red color.

    Parameters
    ----------
    string : str
      string to be printed
    """
    self.colors.print_r(string, end=end)

  def printf(self):
    """
    Return a pretty formatted printable string of config settings.
    """
    string = ["FoBiS.py settings\n"]
    options = vars(self.cliargs)
    for key, value in list(options.items()):
      string.append(str(key) + ": " + str(value))
    return "".join([s + "\n" for s in string])
