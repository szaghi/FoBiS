"""
Compiler.py, module definition of Compiler class.
This is a class designed for handling compilers default support.
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
import re
from .utils import print_fake
__regex_opts__ = re.compile(r"-O[0-9,s]")


class Compiler(object):
  """
  Compiler is an object that handles the compilers default support, its attributes and methods.

  Attributes
  ----------
  supported : {['gnu', 'intel', 'g95']}
    list of supported compilers
  """

  supported = ['gnu', 'intel', 'g95']

  def __init__(self, cliargs, print_w=None):
    """
    Parameters
    ----------
    cliargs : argparse object
    print_w : {None}
      function for printing emphized warning message

    Attributes
    ----------
    compiler : {None}
      str containing compiler vendor name
    fcs : {None}
      str containing compiler statement
    cflags : {None}
      str containing compiling flags
    lflags : {None}
      str containing linking flags
    preproc : {None}
      str containing preprocessing flags
    modsw : {None}
      str containing compiler switch for modules searching path
    mpi : {False}
      activate the MPI compiler
    openmp : {False}
      activate the OpenMP pragmas
    coverage : {False}
      activate the coverage instruments
    profile : {False}
      activate the profile instruments
    print_w : {None}
      function for printing emphized warning message
    """
    if print_w is None:
      self.print_w = print_fake
    else:
      self.print_w = print_w

    self._mpi = None
    self._openmp = None
    self._coverage = None
    self._profile = None
    self.compiler = cliargs.compiler
    if self.compiler:
      if self.compiler.lower() == 'gnu':
        self._gnu()
      elif self.compiler.lower() == 'intel':
        self._intel()
      elif self.compiler.lower() == 'g95':
        self._g95()
      elif self.compiler.lower() == 'custom':
        pass  # set by user options
      else:
        self._gnu()
    # overriding default values if passed
    if cliargs.fc:
      self.fcs = cliargs.fc
    if cliargs.cflags:
      self.cflags = cliargs.cflags
    if cliargs.lflags:
      self.lflags = cliargs.lflags
    if cliargs.preproc:
      self.preproc = cliargs.preproc
    if cliargs.modsw:
      self.modsw = cliargs.modsw
    self.mpi = cliargs.mpi
    self.openmp = cliargs.openmp
    self.coverage = cliargs.coverage
    self.profile = cliargs.profile
    self._set_fcs()
    self._set_cflags()
    self._set_lflags()
    return

  def __str__(self):
    return self.pprint()

  def _gnu(self):
    """Method for setting compiler defaults to the GNU gfortran compiler options."""
    self.compiler = 'gnu'
    self.fcs = 'gfortran'
    self.cflags = '-c'
    self.lflags = ''
    self.preproc = ''
    self.modsw = '-J '
    self._mpi = 'mpif90'
    self._openmp = ['-fopenmp', '-fopenmp']
    self._coverage = ['-ftest-coverage -fprofile-arcs', '-fprofile-arcs']
    self._profile = ['-pg', '-pg']
    return

  def _intel(self):
    """Method for setting compiler defaults to the Intel Fortran compiler options."""
    self.compiler = 'intel'
    self.fcs = 'ifort'
    self.cflags = '-c'
    self.lflags = ''
    self.preproc = ''
    self.modsw = '-module '
    self._mpi = 'mpif90'
    self._openmp = ['-openmp', '-openmp']
    self._coverage = ['-prof-gen=srcpos', '']
    self._profile = ['', '']
    return

  def _g95(self):
    """Method for setting compiler defaults to the g95 compiler options."""
    self.compiler = 'g95'
    self.fcs = 'g95'
    self.cflags = '-c'
    self.lflags = ''
    self.preproc = ''
    self.modsw = '-fmod='
    self._mpi = 'mpif90'
    self._openmp = ['', '']
    self._coverage = ['', '']
    self._profile = ['', '']
    return

  def _set_fcs(self):
    """Method for setting the compiler command statement directly depending on the compiler."""
    if self.compiler.lower() in Compiler.supported:
      if self.mpi:
        self.fcs = self._mpi
    return

  def _set_cflags(self):
    """Method for setting the compiling flags directly depending on the compiler."""
    if self.coverage:
      if self._coverage[0] != '':
        if re.search(__regex_opts__, self.cflags):
          self.print_w('Warning: found optimizations cflags within coverage ones: coverage results can be alterated!')
        self.cflags += ' -O0 ' + self._coverage[0]
    if self.profile:
      if self._profile[0] != '':
        self.cflags += ' ' + self._profile[0]
    if self.openmp:
      if self._openmp[0] != '':
        self.cflags += ' ' + self._openmp[0]
    if self.preproc is not None:
      if self.preproc != '':
        self.cflags += ' ' + self.preproc
    self.cflags = re.sub(r" +", r" ", self.cflags)
    return

  def _set_lflags(self):
    """Method for setting the linking flags directly depending on the compiler."""
    if self.coverage:
      if self._coverage[1] != '':
        if re.search(__regex_opts__, self.lflags):
          self.print_w('Warning: found optimizations lflags within coverage ones: coverage results can be alterated!')
        self.lflags += ' -O0 ' + self._coverage[1]
    if self.profile:
      if self._profile[1] != '':
        self.lflags += ' ' + self._profile[1]
    if self.openmp:
      if self._openmp[1] != '':
        self.lflags += ' ' + self._openmp[1]
    self.lflags = re.sub(r" +", r" ", self.lflags)
    return

  def compile_cmd(self, mod_dir):
    """
    Method returning the compile command accordingly to the compiler options.

    Parameters
    ----------
    mod_dir : str
      path of the modules directory
    """
    return self.fcs + ' ' + self.cflags + ' ' + self.modsw + mod_dir

  def link_cmd(self, mod_dir):
    """
    Method returning the compile command accordingly to the compiler options.

    Parameters
    ----------
    mod_dir : str
      path of the modules directory
    """
    return self.fcs + ' ' + self.lflags + ' ' + self.modsw + mod_dir

  def pprint(self, prefix=''):
    """
    Pretty printer.

    Parameters
    ----------
    prefix : {''}
      prefixing string of each line
    """
    string = prefix + 'Compiler options\n'
    string += prefix + '  Vendor: "' + self.compiler.strip() + '"\n'
    string += prefix + '  Compiler command: "' + self.fcs.strip() + '"\n'
    string += prefix + '  Module directory switch: "' + self.modsw.strip() + '"\n'
    string += prefix + '  Compiling flags: "' + self.cflags.strip() + '"\n'
    string += prefix + '  Linking flags: "' + self.lflags.strip() + '"\n'
    string += prefix + '  Preprocessing flags: "' + self.preproc.strip() + '"\n'
    string += prefix + '  Coverage: ' + str(self.coverage) + '\n'
    if self.coverage:
      string += prefix + '    Coverage compile and link flags: ' + str(self._coverage) + '\n'
    string += prefix + '  Profile: ' + str(self.profile) + '\n'
    if self.profile:
      string += prefix + '    Profile compile and link flags: ' + str(self._profile) + '\n'
    return string
