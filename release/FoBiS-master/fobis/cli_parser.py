"""
CliParser.py, module definition of FoBiS.py CLI Parser object, an istance of argparse.ArgumentParser.
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
import argparse

__extensions_inc__ = [".inc", ".INC", ".h", ".H"]
__extensions_old__ = [".f", ".F", ".for", ".FOR", ".fpp", ".FPP", ".fortran", ".f77", ".F77"]
__extensions_modern__ = [".f90", ".F90", ".f95", ".F95", ".f03", ".F03", ".f08", ".F08", ".f2k", ".F2K"]
__extensions_parsed__ = __extensions_inc__ + __extensions_old__ + __extensions_modern__
__compiler_supported__ = ('gnu', 'intel', 'g95', 'opencoarrays-gnu', 'custom')


def _subparser_compiler(clean=False):
  """
  Construct a cli subparser with the compiler group of arguments.

  Parameters
  ----------
  clean : bool
    activate the clean parser-specific options

  Returns
  -------
  parser : argparse.ArgumentParser()
  """
  parser = argparse.ArgumentParser(add_help=False)
  parser_group = parser.add_argument_group('compiler')
  if clean:
    parser_group.add_argument('-only_obj', required=False, action='store_true', default=False, help='Clean only compiled objects and not also built targets')
    parser_group.add_argument('-only_target', required=False, action='store_true', default=False, help='Clean only built targets and not also compiled objects')
  parser_group.add_argument('-compiler', required=False, action='store', default='gnu', type=str.lower, choices=__compiler_supported__, help='Compiler used (value is case insensitive, default gnu)')
  parser_group.add_argument('-fc', required=False, action='store', default=None, help='Specify the Fortran compiler statement, necessary for custom compiler specification (-compiler Custom)')
  parser_group.add_argument('-cflags', required=False, action='store', default=None, help='Compile flags')
  parser_group.add_argument('-lflags', required=False, action='store', default=None, help='Link flags')
  parser_group.add_argument('-modsw', required=False, action='store', default=None, help='Specify the switch for setting the module searching path, necessary for custom compiler specification (-compiler Custom)')
  parser_group.add_argument('-mpi', required=False, action='store_true', default=False, help='Use MPI enabled version of compiler')
  parser_group.add_argument('-openmp', required=False, action='store_true', default=False, help='Use OpenMP pragmas')
  parser_group.add_argument('-coarray', required=False, action='store_true', default=False, help='Use coarrays')
  parser_group.add_argument('-coverage', required=False, action='store_true', default=False, help='Instrument the built code with coverage analysis tools [default False]')
  parser_group.add_argument('-profile', required=False, action='store_true', default=False, help='Instrument the built code with profiling analysis tools [default False]')
  parser_group.add_argument('-mklib', required=False, action='store', default=None, choices=('static', 'shared'), help='Target library instead of program (use with -target switch)')
  parser_group.add_argument('-ch', '--cflags_heritage', required=False, action='store_true', default=False, help='Store cflags as a heritage for the next build: if cflags change re-compile all')
  parser_group.add_argument('-tb', '--track_build', required=False, action='store_true', default=False, help='Store build infos for the next install command')
  return parser


def _subparser_directories(install=False):
  """
  Construct a cli subparser with the directories group of arguments.

  Returns
  -------
  parser : argparse.ArgumentParser()
  """
  parser = argparse.ArgumentParser(add_help=False)
  parser_group = parser.add_argument_group('directories')
  if install:
    parser_group.add_argument('-dbld', '--build_dir', required=False, action='store', default='./', help='Directory containing built objects [default: ./]')
    parser_group.add_argument('-p', '--prefix', required=False, action='store', default='./', help='Prefix path where built objects are installed')
    parser_group.add_argument('--bin', required=False, action='store', default='bin/', help='Prefix sub-directory where executable files are installed')
    parser_group.add_argument('--lib', required=False, action='store', default='lib/', help='Prefix sub-directory where library files are installed')
    parser_group.add_argument('--include', required=False, action='store', default='include/', help='Prefix sub-directory where include files are installed')
  else:
    parser_group.add_argument('-s', '--src', required=False, action='store', nargs='+', default=['./'], help='Root-directory of source files [default: ./]')
    parser_group.add_argument('-dbld', '--build_dir', required=False, action='store', default='./', help='Directory containing built objects [default: ./]')
    parser_group.add_argument('-dobj', '--obj_dir', required=False, action='store', default='./obj/', help='Directory containing compiled objects [default: ./obj/]')
    parser_group.add_argument('-dmod', '--mod_dir', required=False, action='store', default='./mod/', help='Directory containing .mod files of compiled objects [default: ./mod/]')
    parser_group.add_argument('-dlib', '--lib_dir', required=False, action='store', nargs='+', default=[], help='List of directories searched for libraries [default: None]')
    parser_group.add_argument('-i', '--include', required=False, action='store', nargs='+', default=[], help='List of directories for searching included files')
    parser_group.add_argument('-ed', '--exclude_dirs', required=False, action='store', nargs='+', default=[], help='Exclude a list of directories from the building process')
    parser_group.add_argument('-drs', '--disable_recursive_search', required=False, action='store_true', default=False, help='Disable recursive search inside directories [default False]')
  return parser


def _subparser_files(doctests=False):
  """
  Construct a cli subparser with the files group of arguments.

  Parameters
  ----------
  doctests : bool
    activate the doctests parser-specific options

  Returns
  -------
  parser : argparse.ArgumentParser()
  """
  parser = argparse.ArgumentParser(add_help=False)
  parser_group = parser.add_argument_group('files')
  parser_group.add_argument('-t', '--target', required=False, action='store', default=None, help='Specify a target file [default: all programs found]')
  parser_group.add_argument('-o', '--output', required=False, action='store', default=None, help='Specify the output file name is used with -target switch [default: basename of target]')
  parser_group.add_argument('-e', '--exclude', required=False, action='store', nargs='+', default=[], help='Exclude a list of files from the building process')
  parser_group.add_argument('-libs', required=False, action='store', nargs='+', default=[], help='List of external libraries used that are not into the path: specify with full paths [default: None]')
  parser_group.add_argument('-vlibs', required=False, action='store', nargs='+', default=[], help='List of external libraries used that are not into the path and that are volatile (can change thus triggering re-building): specify with full paths [default: None]')
  parser_group.add_argument('-ext_libs', required=False, action='store', nargs='+', default=[], help='List of external libraries used that are into compiler path [default: None]')
  parser_group.add_argument('-ext_vlibs', required=False, action='store', nargs='+', default=[], help='List of external libraries used that are into compiler path and that are volatile (can change thus triggering re-building) [default: None]')
  parser_group.add_argument('-dependon', required=False, action='store', nargs='+', default=[], help='List of interdependent external fobos file (and mode) for interdependent building [default: None]')
  parser_group.add_argument('-inc', required=False, action='store', nargs='+', default=__extensions_inc__, help='List of extensions for include files [default: ' + str(__extensions_inc__) + ']')
  parser_group.add_argument('-extensions', required=False, action='store', nargs='+', default=__extensions_parsed__, help='List of extensions of parsed files [default: ' + str(__extensions_parsed__) + ']')
  parser_group.add_argument('-build_all', required=False, action='store_true', default=False, help='Build all sources parsed [default False]')
  if doctests:
    parser_group.add_argument('-keep_volatile_doctests', required=False, action='store_true', default=False, help='Keep the volatile doctests programs [default False]')
  return parser


def _subparser_fobos():
  """
  Construct a cli subparser with the fobos group of arguments.

  Returns
  -------
  parser : argparse.ArgumentParser()
  """
  parser = argparse.ArgumentParser(add_help=False)
  parser_group = parser.add_argument_group('fobos')
  parser_group.add_argument('-f', '--fobos', required=False, action='store', default=None, help='Specify a "fobos" file named differently from "fobos"')
  parser_group.add_argument('-fci', '--fobos_case_insensitive', required=False, action='store_true', default=False, help='Assume fobos inputs as case insensitive [defaul: False, case sensitive]')
  parser_group.add_argument('-mode', required=False, action='store', default=None, help='Select a mode defined into a fobos file')
  parser_group.add_argument('-lmodes', required=False, action='store_true', default=False, help='List the modes defined into a fobos file')
  parser_group.add_argument('--print_fobos_template', required=False, action='store_true', default=False, help='Print a comprehensive fobos template')
  return parser


def _subparser_preprocessor():
  """
  Construct a cli subparser with the preprocessor group of arguments.

  Returns
  -------
  parser : argparse.ArgumentParser()
  """
  parser = argparse.ArgumentParser(add_help=False)
  parser_group = parser.add_argument_group('preprocessor')
  parser_group.add_argument('-preprocessor', required=False, action='store', const='PreForM.py', default=None, nargs='?', help='Use the pre-processor for pre-processing sources file; if no preprocessor is specified, PreForM.py is used')
  parser_group.add_argument('-p', '--preproc', required=False, action='store', default=None, help='Preprocessor flags')
  parser_group.add_argument('-dpp', '--preprocessor_dir', required=False, action='store', default=None, help='Directory containing the sources processed by preprocessor [default: none, the processed files are removed after used]')
  parser_group.add_argument('-epp', '--preprocessor_ext', required=False, action='store', nargs='+', default=[], help='List of custom-defined file extensions to be preprocessed by preprocessor [default: none, all files are preprocessed if preprocessor is used]')
  return parser


def _subparser_fancy():
  """
  Construct a cli subparser with the fancy group of arguments.

  Returns
  -------
  parser : argparse.ArgumentParser()
  """
  parser = argparse.ArgumentParser(add_help=False)
  parser_group = parser.add_argument_group('fancy')
  parser_group.add_argument('-force_compile', required=False, action='store_true', default=False, help='Force to (re-)compile all [default: False]')
  parser_group.add_argument('-colors', required=False, action='store_true', default=False, help='Activate colors in shell prints [default: no colors]')
  parser_group.add_argument('-l', '--log', required=False, action='store_true', default=False, help='Activate the creation of a log file [default: no log file]')
  parser_group.add_argument('-graph', required=False, action='store_true', default=False, help='Generate a dependencies graph by means of graphviz [default false]')
  parser_group.add_argument('-q', '--quiet', required=False, action='store_true', default=False, help='Less verbose than default [default false]')
  parser_group.add_argument('-verbose', required=False, action='store_true', default=False, help='Extremely verbose outputs for debugging FoBiS.py [default false]')
  parser_group.add_argument('-j', '--jobs', required=False, action='store', default=1, type=int, help='Specify the number of concurrent jobs used for compiling dependencies [default 1]')
  parser_group.add_argument('-m', '--makefile', required=False, action='store', default=None, help='Generate a GNU Makefile for building the project', metavar='MAKEFILE_name')
  return parser


def _subparser_rules():
  """
  Construct a cli subparser with the rules group of arguments.

  Returns
  -------
  parser : argparse.ArgumentParser()
  """
  parser = argparse.ArgumentParser(add_help=False)
  parser_group = parser.add_argument_group('rules')
  parser_group.add_argument('-ex', '--execute', required=False, action='store', default=None, help='Specify a rule (defined into fobos file) to be executed', metavar='RULE')
  parser_group.add_argument('-ls', '--list', required=False, action='store_true', default=False, help='List the rules defined into a fobos file')
  return parser


def _subparser_rules_intrinsic():
  """
  Construct a cli subparser with the rules_intrinsic group of arguments.

  Returns
  -------
  parser : argparse.ArgumentParser()
  """
  parser = argparse.ArgumentParser(add_help=False)
  parser_group = parser.add_argument_group('intrinsic rules')
  parser_group.add_argument('-get', required=False, action='store', default=None, help='Intrinsic rule for getting options defined into fobos, e.g. -get build_dir')
  parser_group.add_argument('-get_output_name', required=False, action='store_true', default=False, help='Intrinsic rule for getting the final output name accordingly to options defined into fobos')
  parser_group.add_argument('-ford', required=False, action='store', default=None, help='Intrinsic rule for building documentation by means of Ford tool', metavar='project-file.md')
  parser_group.add_argument('-gcov_analyzer', required=False, action='store', default=None, nargs='+', help='Analyze .gcov coverage files saving a report for each file found', metavar='GCOV_REPORTS_DIR [REPORT_SUMMARY_FILE_NAME]')
  return parser


def _parser_build(clisubparsers):
  """
  Construct the build cli parser.

  Parameters
  ----------
  clisubparsers : argparse subparser object
  """
  compiler = _subparser_compiler()
  directories = _subparser_directories()
  files = _subparser_files()
  fobos = _subparser_fobos()
  preprocessor = _subparser_preprocessor()
  fancy = _subparser_fancy()
  buildparser = clisubparsers.add_parser('build', help='Build all programs found or specific target(s)', parents=[compiler, directories, files, fobos, preprocessor, fancy])
  buildparser.set_defaults(which='build')
  return


def _parser_clean(clisubparsers):
  """
  Construct the clean cli parser.

  Parameters
  ----------
  clisubparsers : argparse subparser object
  """
  compiler = _subparser_compiler(clean=True)
  directories = _subparser_directories()
  files = _subparser_files()
  fobos = _subparser_fobos()
  fancy = _subparser_fancy()
  cleanparser = clisubparsers.add_parser('clean', help='Clean project: remove all OBJs and MODs files... use carefully', parents=[compiler, directories, files, fobos, fancy])
  cleanparser.set_defaults(which='clean')
  return


def _parser_rule(clisubparsers):
  """
  Construct the rule cli parser.

  Parameters
  ----------
  clisubparsers : argparse subparser object
  """
  fobos = _subparser_fobos()
  rules = _subparser_rules()
  rules_intrinsic = _subparser_rules_intrinsic()
  fancy = _subparser_fancy()
  rulexparser = clisubparsers.add_parser('rule', help="Execute special rules or user's ones defined into a fobos file", parents=[fobos, rules, rules_intrinsic, fancy])
  rulexparser.set_defaults(which='rule')
  return


def _parser_install(clisubparsers):
  """
  Construct the install cli parser.

  Parameters
  ----------
  clisubparsers : argparse subparser object
  """
  # compiler = _subparser_compiler()
  directories = _subparser_directories(install=True)
  # files = _subparser_files()
  fobos = _subparser_fobos()
  fancy = _subparser_fancy()
  installparser = clisubparsers.add_parser('install', help='Install project files: install previously built files', parents=[directories, fobos, fancy])
  installparser.set_defaults(which='install')
  return


def _parser_doctests(clisubparsers):
  """
  Construct the doctests cli parser.

  Parameters
  ----------
  clisubparsers : argparse subparser object
  """
  compiler = _subparser_compiler()
  directories = _subparser_directories()
  files = _subparser_files(doctests=True)
  fobos = _subparser_fobos()
  preprocessor = _subparser_preprocessor()
  fancy = _subparser_fancy()
  doctestsparser = clisubparsers.add_parser('doctests', help='Test all valid doctests snippets found', parents=[compiler, directories, files, fobos, preprocessor, fancy])
  doctestsparser.set_defaults(which='doctests')
  return


def cli_parser(appname, description, version):
  """
  Create the FoBiS.py Command Line Interface (CLI).

  Parameters
  ----------
  appname : str
    name of the main application
  description : str
    description of the application
  version : str
    current application version
  """
  cliparser = argparse.ArgumentParser(prog=appname,
                                      description=description,
                                      formatter_class=argparse.RawDescriptionHelpFormatter,
                                      epilog="For more detailed commands help use" +
                                      "\n  " + appname + " build -h,--help" +
                                      "\n  " + appname + " clean -h,--help" +
                                      "\n  " + appname + " rule -h,--help" +
                                      "\n  " + appname + " doctests -h,--help")
  cliparser.add_argument('-v', '--version', action='version', help='Show version', version='%(prog)s ' + version)
  clisubparsers = cliparser.add_subparsers(title='Commands', description='Valid commands')
  _parser_build(clisubparsers)
  _parser_clean(clisubparsers)
  _parser_rule(clisubparsers)
  _parser_install(clisubparsers)
  _parser_doctests(clisubparsers)
  return cliparser
