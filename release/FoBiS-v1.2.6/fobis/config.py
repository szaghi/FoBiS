#!/usr/bin/env python
"""
config.py, module definition of FoBiS.py configuration.
"""
import argparse
import os
from .Colors import Colors
__appname__ = "FoBiS.py"
__version__ = "v1.2.6"
__author__ = "Stefano Zaghi"
__author_email__ = "stefano.zaghi@gmail.com"
__license__ = "GNU General Public License v3 (GPLv3)"
__url__ = "https://github.com/szaghi/FoBiS"
__description__ = "a Fortran Building System for poor men"
__long_description__ = "FoBiS.py, a Fortran Building System for poor men, is a KISS tool for automatic building modern Fortran projects, it being able to automatically resolve inter-modules dependancy hierarchy."
# setting CLI
__cliparser__ = argparse.ArgumentParser(prog=__appname__, description='FoBiS.py, Fortran Building System for poor men')
__cliparser__.add_argument('-v', '--version', action='version', help='Show version', version='%(prog)s ' + __version__)
__clisubparsers__ = __cliparser__.add_subparsers(title='Commands', description='Valid commands')
__buildparser__ = __clisubparsers__.add_parser('build', help='Build all programs found or a specific target')
__buildparser__.set_defaults(which='build')
__cleanparser__ = __clisubparsers__.add_parser('clean', help='Clean project: completely remove OBJ and MOD directories... use carefully')
__cleanparser__.set_defaults(which='clean')
__rulexparser__ = __clisubparsers__.add_parser('rule', help='Execute rules defined into a fobos file')
__rulexparser__.set_defaults(which='rule')
__buildparser__.add_argument('-f', '--fobos', required=False, action='store', default=None, help='Specify a "fobos" file named differently from "fobos"')
__buildparser__.add_argument('-colors', required=False, action='store_true', default=False, help='Activate colors in shell prints [default: no colors]')
__buildparser__.add_argument('-l', '--log', required=False, action='store_true', default=False, help='Activate the creation of a log file [default: no log file]')
__buildparser__.add_argument('-q', '--quiet', required=False, action='store_true', default=False, help='Less verbose than default')
__buildparser__.add_argument('-j', '--jobs', required=False, action='store', default=1, type=int, help='Specify the number of concurrent jobs used for compiling dependencies [default 1]')
__buildparser__.add_argument('-compiler', required=False, action='store', default='Intel', help='Compiler used: Intel, GNU, IBM, PGI, g95 or Custom [default: Intel]')
__buildparser__.add_argument('-fc', required=False, action='store', default='', help='Specify the Fortran compiler statement, necessary for custom compiler specification (-compiler Custom)')
__buildparser__.add_argument('-modsw', required=False, action='store', default='', help='Specify the switch for setting the module searching path, necessary for custom compiler specification (-compiler Custom)')
__buildparser__.add_argument('-mpi', required=False, action='store_true', default=False, help='Use MPI enabled version of compiler')
__buildparser__.add_argument('-cflags', required=False, action='store', default='-c', help='Compile flags')
__buildparser__.add_argument('-lflags', required=False, action='store', default='', help='Link flags')
__buildparser__.add_argument('-libs', required=False, action='store', nargs='+', default=[], help='List of external libraries used')
__buildparser__.add_argument('-i', '--include', required=False, action='store', nargs='+', default=[], help='List of directories for searching included files')
__buildparser__.add_argument('-inc', required=False, action='store', nargs='+', default=[], help='List of custom-defined file extensions for include files')
__buildparser__.add_argument('-p', '--preproc', required=False, action='store', default='', help='Preprocessor flags')
__buildparser__.add_argument('-dobj', '--obj_dir', required=False, action='store', default='./obj/', help='Directory containing compiled objects [default: ./obj/]')
__buildparser__.add_argument('-dmod', '--mod_dir', required=False, action='store', default='./mod/', help='Directory containing .mod files of compiled objects [default: ./mod/]')
__buildparser__.add_argument('-dbld', '--build_dir', required=False, action='store', default='./', help='Directory containing executable objects [default: ./]')
__buildparser__.add_argument('-s', '--src', required=False, action='store', default='./', help='Root-directory of source files [default: ./]')
__buildparser__.add_argument('-e', '--exclude', required=False, action='store', nargs='+', default=[], help='Exclude a list of files from the building process')
__buildparser__.add_argument('-t', '--target', required=False, action='store', default=None, help='Specify a target file [default: all programs found]')
__buildparser__.add_argument('-o', '--output', required=False, action='store', default=None, help='Specify the output file name is used with -target switch [default: basename of target]')
__buildparser__.add_argument('-mklib', required=False, action='store', default=None, help='Build library instead of program (use with -target switch); usage: -mklib static or -mklib shared')
__buildparser__.add_argument('-mode', required=False, action='store', default=None, help='Select a mode defined into a fobos file')
__buildparser__.add_argument('-lmodes', required=False, action='store_true', default=False, help='List the modes defined into a fobos file')
__buildparser__.add_argument('-m', '--makefile', required=False, action='store', default=None, help='Generate a GNU Makefile for building the project', metavar='MAKEFILE_name')
__buildparser__.add_argument('-pfm', '--preform', required=False, action='store_true', default=False, help='Use PreForM.py pre-processor for pre-processing sources file')
__buildparser__.add_argument('-dpfm', '--pfm_dir', required=False, action='store', default=None, help='Directory containing the sources processed with PreForM.py [default: none, the processed files are removed after used]')
__buildparser__.add_argument('-epfm', '--pfm_ext', required=False, action='store', nargs='+', default=[], help='List of custom-defined file extensions to be preprocessed by PreForM.py [default: none, all files are preprocessed if PreForM.py is used]')
__cleanparser__.add_argument('-f', '--fobos', required=False, action='store', default=None, help='Specify a "fobos" file named differently from "fobos"')
__cleanparser__.add_argument('-colors', required=False, action='store_true', default=False, help='Activate colors in shell prints [default: no colors]')
__cleanparser__.add_argument('-dobj', '--obj_dir', required=False, action='store', default='./obj/', help='Directory containing compiled objects [default: ./obj/]')
__cleanparser__.add_argument('-dmod', '--mod_dir', required=False, action='store', default='./mod/', help='Directory containing .mod files of compiled objects [default: ./mod/]')
__cleanparser__.add_argument('-dbld', '--build_dir', required=False, action='store', default='./', help='Directory containing executable objects [default: ./]')
__cleanparser__.add_argument('-t', '--target', required=False, action='store', default=None, help='Specify a target file [default: all programs found]')
__cleanparser__.add_argument('-o', '--output', required=False, action='store', default=None, help='Specify the output file name is used with -target switch [default: basename of target]')
__cleanparser__.add_argument('-only_obj', required=False, action='store_true', default=False, help='Clean only compiled objects and not also built targets')
__cleanparser__.add_argument('-only_target', required=False, action='store_true', default=False, help='Clean only built targets and not also compiled objects')
__cleanparser__.add_argument('-mklib', required=False, action='store', default=None, help='Build library instead of program (use with -target switch); usage: -mklib static or -mklib shared')
__cleanparser__.add_argument('-mode', required=False, action='store', default=None, help='Select a mode defined into a fobos file')
__cleanparser__.add_argument('-lmodes', required=False, action='store_true', default=False, help='List the modes defined into a fobos file')
__rulexparser__.add_argument('-f', '--fobos', required=False, action='store', default=None, help='Specify a "fobos" file named differently from "fobos"')
__rulexparser__.add_argument('-ex', '--execute', required=False, action='store', default=None, help='Specify a rule (defined into fobos file) to be executed', metavar='RULE')
__rulexparser__.add_argument('-ls', '--list', required=False, action='store_true', default=False, help='List the rules defined into a fobos file')
__rulexparser__.add_argument('-q', '--quiet', required=False, action='store_true', default=False, help='Less verbose than default')


class FoBiSConfig(object):
  """
  Object handling FoBiS.py configuration
  """
  def __init__(self):
    """
    Attributes
    ----------
    quiet : bool
      less verbose printing messages (default no)
    extensions_inc : list
      list of extensions of included files
    extensions_old : list
      list of extensions of old Fortran format parsed
    extensions_modern : list
      list of extensions of modern Fortran format parsed
    extensions_parsed : list
      list of extensions of Fortran format parsed
    cliargs : argparse object
      CLI arguments
    """
    self.quiet = False
    self.colors = Colors()
    self.extensions_inc = [".inc", ".INC", ".h", ".H"]
    self.extensions_old = [".f", ".F", ".for", ".FOR", ".fpp", ".FPP", ".fortran", ".f77", ".F77"]
    self.extensions_modern = [".f90", ".F90", ".f95", ".F95", ".f03", ".F03", ".f08", ".F08", ".f2k", ".F2K"]
    self.extensions_parsed = self.extensions_old + self.extensions_modern
    self.cliargs = None
    return

  def __str__(self):
    string = ['FoBiS.py configuration']
    string.append('\n  Quiet mode: ' + str(self.quiet))
    string.append('\n  Extensions of included files: ' + str(self.extensions_inc))
    string.append('\n  Extensions of parsed files:   ' + str(self.extensions_parsed))
    return ''.join(string)

  def printf(self):
    """Method for printing config data. It checks verbosity."""
    if not self.quiet:
      print(self)
    return

  def get_cli(self):
    """Method for parsing CLI arguments."""
    self.cliargs = __cliparser__.parse_args()
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

# global variables
__initialized__ = False
if not __initialized__:
  __config__ = FoBiSConfig()
  __initialized__ = True
