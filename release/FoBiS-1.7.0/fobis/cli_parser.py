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


def _build_parser(clisubparsers):
  """
  Function for constructing the build cli parser.

  Parameters
  ----------
  clisubparsers : argparse subparser object
  """
  buildparser = clisubparsers.add_parser('build', help='Build all programs found or specific target(s)')
  buildparser.set_defaults(which='build')
  buildparser_g_compiler = buildparser.add_argument_group('compiler')
  buildparser_g_compiler.add_argument('-compiler', required=False, action='store', default='intel', type=str.lower, choices=('gnu', 'intel', 'g95', 'custom'), help='Compiler used (value is case insensitive, default intel)')
  buildparser_g_compiler.add_argument('-fc', required=False, action='store', default=None, help='Specify the Fortran compiler statement, necessary for custom compiler specification (-compiler Custom)')
  buildparser_g_compiler.add_argument('-cflags', required=False, action='store', default=None, help='Compile flags')
  buildparser_g_compiler.add_argument('-lflags', required=False, action='store', default=None, help='Link flags')
  buildparser_g_compiler.add_argument('-p', '--preproc', required=False, action='store', default=None, help='Preprocessor flags')
  buildparser_g_compiler.add_argument('-modsw', required=False, action='store', default=None, help='Specify the switch for setting the module searching path, necessary for custom compiler specification (-compiler Custom)')
  buildparser_g_compiler.add_argument('-mpi', required=False, action='store_true', default=False, help='Use MPI enabled version of compiler')
  buildparser_g_compiler.add_argument('-openmp', required=False, action='store_true', default=False, help='Use OpenMP pragmas')
  buildparser_g_compiler.add_argument('-coverage', required=False, action='store_true', default=False, help='Instrument the built code with coverage analysis tools [default False]')
  buildparser_g_compiler.add_argument('-profile', required=False, action='store_true', default=False, help='Instrument the built code with profiling analysis tools [default False]')
  buildparser_g_compiler.add_argument('-mklib', required=False, action='store', default=None, choices=('static', 'shared'), help='Build library instead of program (use with -target switch)')
  buildparser_g_compiler.add_argument('-ch', '--cflags_heritage', required=False, action='store_true', default=False, help='Store cflags as a heritage for the next build: if cflags change re-compile all')
  buildparser_g_dirs = buildparser.add_argument_group('directories')
  buildparser_g_dirs.add_argument('-s', '--src', required=False, action='store', default='./', help='Root-directory of source files [default: ./]')
  buildparser_g_dirs.add_argument('-dbld', '--build_dir', required=False, action='store', default='./', help='Directory containing executable objects [default: ./]')
  buildparser_g_dirs.add_argument('-dobj', '--obj_dir', required=False, action='store', default='./obj/', help='Directory containing compiled objects [default: ./obj/]')
  buildparser_g_dirs.add_argument('-dmod', '--mod_dir', required=False, action='store', default='./mod/', help='Directory containing .mod files of compiled objects [default: ./mod/]')
  buildparser_g_dirs.add_argument('-dlib', '--lib_dir', required=False, action='store', nargs='+', default=[], help='List of directories searched for libraries [default: None]')
  buildparser_g_dirs.add_argument('-i', '--include', required=False, action='store', nargs='+', default=[], help='List of directories for searching included files')
  buildparser_g_files = buildparser.add_argument_group('files')
  buildparser_g_files.add_argument('-t', '--target', required=False, action='store', default=None, help='Specify a target file [default: all programs found]')
  buildparser_g_files.add_argument('-o', '--output', required=False, action='store', default=None, help='Specify the output file name is used with -target switch [default: basename of target]')
  buildparser_g_files.add_argument('-e', '--exclude', required=False, action='store', nargs='+', default=[], help='Exclude a list of files from the building process')
  buildparser_g_files.add_argument('-libs', required=False, action='store', nargs='+', default=[], help='List of external libraries used that are not into the path: specify with full paths [default: None]')
  buildparser_g_files.add_argument('-vlibs', required=False, action='store', nargs='+', default=[], help='List of external libraries used that are not into the path and that are volatile (can change thus triggering re-building): specify with full paths [default: None]')
  buildparser_g_files.add_argument('-ext_libs', required=False, action='store', nargs='+', default=[], help='List of external libraries used that are into compiler path [default: None]')
  buildparser_g_files.add_argument('-ext_vlibs', required=False, action='store', nargs='+', default=[], help='List of external libraries used that are into compiler path and that are volatile (can change thus triggering re-building) [default: None]')
  buildparser_g_files.add_argument('-dependon', required=False, action='store', nargs='+', default=[], help='List of interdependent external fobos file (and mode) for interdependent building [default: None]')
  buildparser_g_files.add_argument('-inc', required=False, action='store', nargs='+', default=__extensions_inc__, help='List of extensions for include files [default: ' + str(__extensions_inc__) + ']')
  buildparser_g_files.add_argument('-extensions', required=False, action='store', nargs='+', default=__extensions_parsed__, help='List of extensions of parsed files [default: ' + str(__extensions_parsed__) + ']')
  buildparser_g_fobos = buildparser.add_argument_group('fobos')
  buildparser_g_fobos.add_argument('-f', '--fobos', required=False, action='store', default=None, help='Specify a "fobos" file named differently from "fobos"')
  buildparser_g_fobos.add_argument('-fci', '--fobos_case_insensitive', required=False, action='store_true', default=False, help='Assume fobos inputs as case insensitive [defaul: False, case sensitive]')
  buildparser_g_fobos.add_argument('-mode', required=False, action='store', default=None, help='Select a mode defined into a fobos file')
  buildparser_g_fobos.add_argument('-lmodes', required=False, action='store_true', default=False, help='List the modes defined into a fobos file')
  buildparser_g_preform = buildparser.add_argument_group('PreForM.py')
  buildparser_g_preform.add_argument('-pfm', '--preform', required=False, action='store_true', default=False, help='Use PreForM.py pre-processor for pre-processing sources file')
  buildparser_g_preform.add_argument('-dpfm', '--pfm_dir', required=False, action='store', default=None, help='Directory containing the sources processed with PreForM.py [default: none, the processed files are removed after used]')
  buildparser_g_preform.add_argument('-epfm', '--pfm_ext', required=False, action='store', nargs='+', default=[], help='List of custom-defined file extensions to be preprocessed by PreForM.py [default: none, all files are preprocessed if PreForM.py is used]')
  buildparser_g_fancy = buildparser.add_argument_group('fancy')
  buildparser_g_fancy.add_argument('-force_compile', required=False, action='store_true', default=False, help='Force to (re-)compile all [default: False]')
  buildparser_g_fancy.add_argument('-colors', required=False, action='store_true', default=False, help='Activate colors in shell prints [default: no colors]')
  buildparser_g_fancy.add_argument('-l', '--log', required=False, action='store_true', default=False, help='Activate the creation of a log file [default: no log file]')
  buildparser_g_fancy.add_argument('-graph', required=False, action='store_true', default=False, help='Generate a dependencies graph by means of graphviz [default false]')
  buildparser_g_fancy.add_argument('-q', '--quiet', required=False, action='store_true', default=False, help='Less verbose than default [default false]')
  buildparser_g_fancy.add_argument('-verbose', required=False, action='store_true', default=False, help='Extremely verbose outputs for debugging FoBiS.py [default false]')
  buildparser_g_fancy.add_argument('-j', '--jobs', required=False, action='store', default=1, type=int, help='Specify the number of concurrent jobs used for compiling dependencies [default 1]')
  buildparser_g_fancy.add_argument('-m', '--makefile', required=False, action='store', default=None, help='Generate a GNU Makefile for building the project', metavar='MAKEFILE_name')
  return


def _clean_parser(clisubparsers):
  """
  Function for constructing the clean cli parser.

  Parameters
  ----------
  clisubparsers : argparse subparser object
  """
  cleanparser = clisubparsers.add_parser('clean', help='Clean project: remove all OBJs and MODs files... use carefully')
  cleanparser.set_defaults(which='clean')
  cleanparser_g_compiler = cleanparser.add_argument_group('compiler')
  cleanparser_g_compiler.add_argument('-only_obj', required=False, action='store_true', default=False, help='Clean only compiled objects and not also built targets')
  cleanparser_g_compiler.add_argument('-only_target', required=False, action='store_true', default=False, help='Clean only built targets and not also compiled objects')
  cleanparser_g_compiler.add_argument('-mklib', required=False, action='store', default=None, help='Build library instead of program (use with -target switch); usage: -mklib static or -mklib shared')
  cleanparser_g_compiler.add_argument('-ch', '--cflags_heritage', required=False, action='store_true', default=False, help='Store cflags as a heritage for the next build: if cflags change re-compile all')
  cleanparser_g_compiler.add_argument('-coverage', required=False, action='store_true', default=False, help='Clean files used for performing coverage analysis [default False]')
  cleanparser_g_dirs = cleanparser.add_argument_group('directories')
  cleanparser_g_dirs.add_argument('-dobj', '--obj_dir', required=False, action='store', default='./obj/', help='Directory containing compiled objects [default: ./obj/]')
  cleanparser_g_dirs.add_argument('-dmod', '--mod_dir', required=False, action='store', default='./mod/', help='Directory containing .mod files of compiled objects [default: ./mod/]')
  cleanparser_g_dirs.add_argument('-dbld', '--build_dir', required=False, action='store', default='./', help='Directory containing executable objects [default: ./]')
  cleanparser_g_files = cleanparser.add_argument_group('files')
  cleanparser_g_files.add_argument('-t', '--target', required=False, action='store', default=None, help='Specify a target file [default: all programs found]')
  cleanparser_g_files.add_argument('-o', '--output', required=False, action='store', default=None, help='Specify the output file name is used with -target switch [default: basename of target]')
  cleanparser_g_files.add_argument('-extensions', required=False, action='store', nargs='+', default=__extensions_parsed__, help='List of extensions of parsed files [default: ' + str(__extensions_parsed__) + ']')
  cleanparser_g_fobos = cleanparser.add_argument_group('fobos')
  cleanparser_g_fobos.add_argument('-f', '--fobos', required=False, action='store', default=None, help='Specify a "fobos" file named differently from "fobos"')
  cleanparser_g_fobos.add_argument('-fci', '--fobos_case_insensitive', required=False, action='store_true', default=False, help='Assume fobos inputs as case insensitive [defaul: False, case sensitive]')
  cleanparser_g_fobos.add_argument('-mode', required=False, action='store', default=None, help='Select a mode defined into a fobos file')
  cleanparser_g_fobos.add_argument('-lmodes', required=False, action='store_true', default=False, help='List the modes defined into a fobos file')
  cleanparser_g_fancy = cleanparser.add_argument_group('fancy')
  cleanparser_g_fancy.add_argument('-colors', required=False, action='store_true', default=False, help='Activate colors in shell prints [default: no colors]')
  cleanparser_g_fancy.add_argument('-q', '--quiet', required=False, action='store_true', default=False, help='Less verbose than default [default false]')
  cleanparser_g_fancy.add_argument('-verbose', required=False, action='store_true', default=False, help='Extremely verbose outputs for debugging FoBiS.py [default false]')
  return


def _rule_parser(clisubparsers):
  """
  Function for constructing the rule cli parser.

  Parameters
  ----------
  clisubparsers : argparse subparser object
  """
  rulexparser = clisubparsers.add_parser('rule', help="Execute special rules or user's ones defined into a fobos file")
  rulexparser.set_defaults(which='rule')
  rulexparser_g_fobos = rulexparser.add_argument_group('fobos file')
  rulexparser_g_fobos.add_argument('-f', '--fobos', required=False, action='store', default=None, help='Specify a "fobos" file named differently from "fobos"')
  rulexparser_g_fobos.add_argument('-mode', required=False, action='store', default=None, help='Select a mode defined into a fobos file')
  rulexparser_g_fobos.add_argument('-fci', '--fobos_case_insensitive', required=False, action='store_true', default=False, help='Assume fobos inputs as case insensitive [defaul: False, case sensitive]')
  rulexparser_g_rules = rulexparser.add_argument_group('rules')
  rulexparser_g_rules.add_argument('-ex', '--execute', required=False, action='store', default=None, help='Specify a rule (defined into fobos file) to be executed', metavar='RULE')
  rulexparser_g_rules.add_argument('-ls', '--list', required=False, action='store_true', default=False, help='List the rules defined into a fobos file')
  rulexparser_g_intrinsic = rulexparser.add_argument_group('intrinsic rules')
  rulexparser_g_intrinsic.add_argument('-get', required=False, action='store', default=None, help='Intrinsic rule for getting options defined into fobos, e.g. -get build_dir')
  rulexparser_g_intrinsic.add_argument('-get_output_name', required=False, action='store_true', default=False, help='Intrinsic rule for getting the final output name accordingly to options defined into fobos')
  rulexparser_g_intrinsic.add_argument('-ford', required=False, action='store', default=None, help='Intrinsic rule for building documentation by means of Ford tool', metavar='project-file.md')
  rulexparser_g_intrinsic.add_argument('-gcov_analyzer', required=False, action='store', default=None, nargs='+', help='Analyze .gcov coverage files saving a report for each file found', metavar='GCOV_REPORTS_DIR [REPORT_SUMMARY_FILE_NAME]')
  rulexparser_g_fancy = rulexparser.add_argument_group('fancy')
  rulexparser_g_fancy.add_argument('-q', '--quiet', required=False, action='store_true', default=False, help='Less verbose than default [default false]')
  rulexparser_g_fancy.add_argument('-verbose', required=False, action='store_true', default=False, help='Extremely verbose outputs for debugging FoBiS.py [default false]')
  rulexparser_g_fancy.add_argument('-colors', required=False, action='store_true', default=False, help='Activate colors in shell prints [default: no colors]')
  return


def cli_parser(appname, description, version):
  """
  Function for creating the FoBiS.py Command Line Interface.

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
                                      "\n  " + appname + " rule -h,--help")
  cliparser.add_argument('-v', '--version', action='version', help='Show version', version='%(prog)s ' + version)
  clisubparsers = cliparser.add_subparsers(title='Commands', description='Valid commands')

  _build_parser(clisubparsers)
  _clean_parser(clisubparsers)
  _rule_parser(clisubparsers)
  return cliparser
