#!/usr/bin/env python
"""
config.py, module definition of FoBiS.py configuration.
"""
import argparse
import os
from .Colors import Colors
__appname__ = "FoBiS.py"
__version__ = "v1.3.0"
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
__buildparser_g_compiler__ = __buildparser__.add_argument_group('compiler')
__buildparser_g_compiler__.add_argument('-compiler', required=False, action='store', default='intel', type=str.lower, choices=('gnu', 'intel', 'g95', 'custom'), help='Compiler used (value is case insensitive, default intel)')
__buildparser_g_compiler__.add_argument('-fc', required=False, action='store', default='', help='Specify the Fortran compiler statement, necessary for custom compiler specification (-compiler Custom)')
__buildparser_g_compiler__.add_argument('-cflags', required=False, action='store', default='-c', help='Compile flags')
__buildparser_g_compiler__.add_argument('-lflags', required=False, action='store', default='', help='Link flags')
__buildparser_g_compiler__.add_argument('-p', '--preproc', required=False, action='store', default='', help='Preprocessor flags')
__buildparser_g_compiler__.add_argument('-modsw', required=False, action='store', default='', help='Specify the switch for setting the module searching path, necessary for custom compiler specification (-compiler Custom)')
__buildparser_g_compiler__.add_argument('-mpi', required=False, action='store_true', default=False, help='Use MPI enabled version of compiler')
__buildparser_g_compiler__.add_argument('-mklib', required=False, action='store', default=None, choices=('static', 'shared'), help='Build library instead of program (use with -target switch)')
__buildparser_g_compiler__.add_argument('-ch', '--cflags_heritage', required=False, action='store_true', default=False, help='Store cflags as a heritage for the next build: if cflags change re-compile all')
__buildparser_g_dirs__ = __buildparser__.add_argument_group('directories')
__buildparser_g_dirs__.add_argument('-s', '--src', required=False, action='store', default='./', help='Root-directory of source files [default: ./]')
__buildparser_g_dirs__.add_argument('-dbld', '--build_dir', required=False, action='store', default='./', help='Directory containing executable objects [default: ./]')
__buildparser_g_dirs__.add_argument('-dobj', '--obj_dir', required=False, action='store', default='./obj/', help='Directory containing compiled objects [default: ./obj/]')
__buildparser_g_dirs__.add_argument('-dmod', '--mod_dir', required=False, action='store', default='./mod/', help='Directory containing .mod files of compiled objects [default: ./mod/]')
__buildparser_g_dirs__.add_argument('-dlib', '--lib_dir', required=False, action='store', nargs='+', default=[], help='List of directories searched for libraries [default: None]')
__buildparser_g_dirs__.add_argument('-i', '--include', required=False, action='store', nargs='+', default=[], help='List of directories for searching included files')
__buildparser_g_files__ = __buildparser__.add_argument_group('files')
__buildparser_g_files__.add_argument('-t', '--target', required=False, action='store', default=None, help='Specify a target file [default: all programs found]')
__buildparser_g_files__.add_argument('-o', '--output', required=False, action='store', default=None, help='Specify the output file name is used with -target switch [default: basename of target]')
__buildparser_g_files__.add_argument('-e', '--exclude', required=False, action='store', nargs='+', default=[], help='Exclude a list of files from the building process')
__buildparser_g_files__.add_argument('-inc', required=False, action='store', nargs='+', default=[], help='List of custom-defined file extensions for include files')
__buildparser_g_files__.add_argument('-libs', required=False, action='store', nargs='+', default=[], help='List of external libraries use that are dnot into the path: specify with full paths [default: None]')
__buildparser_g_files__.add_argument('-ext_libs', required=False, action='store', nargs='+', default=[], help='List of external libraries used that are into compiler path [default: None]')
__buildparser_g_fobos__ = __buildparser__.add_argument_group('fobos')
__buildparser_g_fobos__.add_argument('-f', '--fobos', required=False, action='store', default=None, help='Specify a "fobos" file named differently from "fobos"')
__buildparser_g_fobos__.add_argument('-fci', '--fobos_case_insensitive', required=False, action='store_true', default=False, help='Assume fobos inputs as case insensitive [defaul: False, case sensitive]')
__buildparser_g_fobos__.add_argument('-mode', required=False, action='store', default=None, help='Select a mode defined into a fobos file')
__buildparser_g_fobos__.add_argument('-lmodes', required=False, action='store_true', default=False, help='List the modes defined into a fobos file')
__buildparser_g_preform__ = __buildparser__.add_argument_group('PreForM.py')
__buildparser_g_preform__.add_argument('-pfm', '--preform', required=False, action='store_true', default=False, help='Use PreForM.py pre-processor for pre-processing sources file')
__buildparser_g_preform__.add_argument('-dpfm', '--pfm_dir', required=False, action='store', default=None, help='Directory containing the sources processed with PreForM.py [default: none, the processed files are removed after used]')
__buildparser_g_preform__.add_argument('-epfm', '--pfm_ext', required=False, action='store', nargs='+', default=[], help='List of custom-defined file extensions to be preprocessed by PreForM.py [default: none, all files are preprocessed if PreForM.py is used]')
__buildparser_g_fancy__ = __buildparser__.add_argument_group('fancy')
__buildparser_g_fancy__.add_argument('-colors', required=False, action='store_true', default=False, help='Activate colors in shell prints [default: no colors]')
__buildparser_g_fancy__.add_argument('-l', '--log', required=False, action='store_true', default=False, help='Activate the creation of a log file [default: no log file]')
__buildparser_g_fancy__.add_argument('-q', '--quiet', required=False, action='store_true', default=False, help='Less verbose than default')
__buildparser_g_fancy__.add_argument('-j', '--jobs', required=False, action='store', default=1, type=int, help='Specify the number of concurrent jobs used for compiling dependencies [default 1]')
__buildparser_g_fancy__.add_argument('-m', '--makefile', required=False, action='store', default=None, help='Generate a GNU Makefile for building the project', metavar='MAKEFILE_name')

__cleanparser__ = __clisubparsers__.add_parser('clean', help='Clean project: completely remove OBJ and MOD directories... use carefully')
__cleanparser__.set_defaults(which='clean')
__cleanparser_g_compiler__ = __cleanparser__.add_argument_group('compiler')
__cleanparser_g_compiler__.add_argument('-only_obj', required=False, action='store_true', default=False, help='Clean only compiled objects and not also built targets')
__cleanparser_g_compiler__.add_argument('-only_target', required=False, action='store_true', default=False, help='Clean only built targets and not also compiled objects')
__cleanparser_g_compiler__.add_argument('-mklib', required=False, action='store', default=None, help='Build library instead of program (use with -target switch); usage: -mklib static or -mklib shared')
__cleanparser_g_dirs__ = __cleanparser__.add_argument_group('directories')
__cleanparser_g_dirs__.add_argument('-dobj', '--obj_dir', required=False, action='store', default='./obj/', help='Directory containing compiled objects [default: ./obj/]')
__cleanparser_g_dirs__.add_argument('-dmod', '--mod_dir', required=False, action='store', default='./mod/', help='Directory containing .mod files of compiled objects [default: ./mod/]')
__cleanparser_g_dirs__.add_argument('-dbld', '--build_dir', required=False, action='store', default='./', help='Directory containing executable objects [default: ./]')
__cleanparser_g_files__ = __cleanparser__.add_argument_group('files')
__cleanparser_g_files__.add_argument('-t', '--target', required=False, action='store', default=None, help='Specify a target file [default: all programs found]')
__cleanparser_g_files__.add_argument('-o', '--output', required=False, action='store', default=None, help='Specify the output file name is used with -target switch [default: basename of target]')
__cleanparser_g_fobos__ = __cleanparser__.add_argument_group('fobos')
__cleanparser_g_fobos__.add_argument('-f', '--fobos', required=False, action='store', default=None, help='Specify a "fobos" file named differently from "fobos"')
__cleanparser_g_fobos__.add_argument('-fci', '--fobos_case_insensitive', required=False, action='store_true', default=False, help='Assume fobos inputs as case insensitive [defaul: False, case sensitive]')
__cleanparser_g_fobos__.add_argument('-mode', required=False, action='store', default=None, help='Select a mode defined into a fobos file')
__cleanparser_g_fobos__.add_argument('-lmodes', required=False, action='store_true', default=False, help='List the modes defined into a fobos file')
__cleanparser_g_fancy__ = __cleanparser__.add_argument_group('fancy')
__cleanparser_g_fancy__.add_argument('-colors', required=False, action='store_true', default=False, help='Activate colors in shell prints [default: no colors]')

__rulexparser__ = __clisubparsers__.add_parser('rule', help='Execute rules defined into a fobos file')
__rulexparser__.set_defaults(which='rule')
__rulexparser__.add_argument('-f', '--fobos', required=False, action='store', default=None, help='Specify a "fobos" file named differently from "fobos"')
__rulexparser__.add_argument('-fci', '--fobos_case_insensitive', required=False, action='store_true', default=False, help='Assume fobos inputs as case insensitive [defaul: False, case sensitive]')
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
    if fake_args:
      self.cliargs = __cliparser__.parse_args(fake_args)
    else:
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

  def check_cflags_heritage(self):
    """Method for checking the heritage of cflags: if a file named '.cflags.heritage' is found into the root dir FoBiS.py is runned that file
    is sourced and compared with the actual cflags and in case they differ the project is forced to be recompiled. The actual cflags are saved,
    in any case, into that file."""
    if self.cliargs.which == 'build':
      if self.cliargs.cflags_heritage:
        if os.path.exists('.cflags.heritage'):
          cflags_old = open('.cflags.heritage').read()
          if self.cliargs.cflags != cflags_old:
            self.force_compile = True
            print(self.colors.red + "The present cflags are different from the heritages one: forcing to (re-)compile all" + self.colors.end)
        with open('.cflags.heritage', 'w') as chf:
          chf.writelines(self.cliargs.cflags)
    return

# global variables
__initialized__ = False
if not __initialized__:
  __config__ = FoBiSConfig()
  __initialized__ = True
