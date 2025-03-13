#!/usr/bin/env python
"""
FoBiS.py, Fortran Building System for poor men
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
# modules loading
from __future__ import print_function
from __future__ import absolute_import
from __future__ import division
from __future__ import unicode_literals
from future import standard_library
standard_library.install_aliases()
from builtins import *
try:
  import configparser as configparser
except ImportError:
  import configparser
import os
import shutil
import sys
from .Builder import Builder
from .Cleaner import Cleaner
from .FoBiSConfig import FoBiSConfig
from .Gcov import Gcov
from .ParsedFile import ParsedFile
from .utils import dependency_hiearchy
from .utils import remove_other_main
from .utils import syswork
from .utils import safe_mkdir


def main():
  """
  Main function.
  """
  run_fobis()
  sys.exit(0)


def run_fobis(fake_args=None):
  """
  Run FoBiS accordingly to the user configuration.

  Parameters
  ----------
  fake_args : list
    list containing fake CLAs for using without CLI
  """
  configuration = FoBiSConfig(fake_args=fake_args)
  if configuration.cliargs.which == 'rule':
    run_fobis_rule(configuration)
  else:
    if configuration.cliargs.lmodes:
      configuration.fobos.modes_list()
      sys.exit(0)
    if configuration.cliargs.print_fobos_template:
      configuration.fobos.print_template(configuration.cliargs)
      sys.exit(0)
    if configuration.cliargs.which == 'clean':
      run_fobis_clean(configuration)
    if configuration.cliargs.which == 'build':
      run_fobis_build(configuration)
    if configuration.cliargs.which == 'install':
      run_fobis_install(configuration)
    if configuration.cliargs.which == 'doctests':
      run_fobis_doctests(configuration)
  return


def run_fobis_build(configuration):
  """
  Run FoBiS in build mode.

  Parameters
  ----------
  configuration : FoBiSConfig()
  """

  pfiles = parse_files(configuration=configuration)
  builder = Builder(cliargs=configuration.cliargs, print_n=configuration.print_b, print_w=configuration.print_r)
  dependency_hiearchy(builder=builder, pfiles=pfiles, print_w=configuration.print_r, force_compile=configuration.cliargs.force_compile)
  if configuration.cliargs.makefile:
    save_makefile(configuration=configuration, pfiles=pfiles, builder=builder)
    return
  nomodlibs = build_nomodlibs(configuration=configuration, pfiles=pfiles, builder=builder)
  submodules = build_submodules(configuration=configuration, pfiles=pfiles, builder=builder)
  # building target or all programs found
  for pfile in pfiles:
    if configuration.cliargs.build_all:
      build_pfile(configuration=configuration, pfile=pfile, pfiles=pfiles, nomodlibs=nomodlibs, submodules=submodules, builder=builder)
    else:
      if configuration.cliargs.target:
        if os.path.basename(configuration.cliargs.target) == os.path.basename(pfile.name):
          build_pfile(configuration=configuration, pfile=pfile, pfiles=pfiles, nomodlibs=nomodlibs, submodules=submodules, builder=builder)
      else:
        if pfile.program:
          build_pfile(configuration=configuration, pfile=pfile, pfiles=pfiles, nomodlibs=nomodlibs, submodules=submodules, builder=builder)


def run_fobis_clean(configuration):
  """
  Run FoBiS in build mode.

  Parameters
  ----------
  configuration : FoBiSConfig()
  """
  cleaner = Cleaner(cliargs=configuration.cliargs, print_w=configuration.print_r)
  if not configuration.cliargs.only_obj and not configuration.cliargs.only_target:
    cleaner.clean_mod()
    cleaner.clean_obj()
    cleaner.clean_target()
  if configuration.cliargs.only_obj:
    cleaner.clean_mod()
    cleaner.clean_obj()
  if configuration.cliargs.only_target:
    cleaner.clean_target()


def run_fobis_rule(configuration):
  """
  Run FoBiS in build mode.

  Parameters
  ----------
  configuration : FoBiSConfig()
  """
  if configuration.cliargs.list:
    configuration.fobos.rules_list(quiet=configuration.cliargs.quiet)
  elif configuration.cliargs.execute:
    configuration.fobos.rule_execute(rule=configuration.cliargs.execute, quiet=configuration.cliargs.quiet)
  elif configuration.cliargs.get:
    configuration.fobos.get(option=configuration.cliargs.get, mode=configuration.cliargs.mode)
  elif configuration.cliargs.get_output_name:
    configuration.fobos.get_output_name(mode=configuration.cliargs.mode)
  elif configuration.cliargs.ford:
    result = syswork("ford " + configuration.cliargs.ford)
    if result[0] != 0:
      configuration.print_r(result[1])
    else:
      configuration.print_b(result[1])
  elif configuration.cliargs.gcov_analyzer:
    gcov_analyzer(configuration=configuration)
  elif configuration.cliargs.is_ascii_kind_supported:
    is_ascii_kind_supported(configuration=configuration)
  elif configuration.cliargs.is_ucs4_kind_supported:
    is_ucs4_kind_supported(configuration=configuration)
  elif configuration.cliargs.is_float128_kind_supported:
    is_float128_kind_supported(configuration=configuration)


def run_fobis_install(configuration):
  """
  Run FoBiS in install mode.

  Parameters
  ----------
  configuration : FoBiSConfig()
  """

  if not os.path.exists(configuration.cliargs.build_dir):
    configuration.fobos.print_w('Error: build directory not found! Maybe you have to run "FoBiS.py build" before.')
    sys.exit(1)
  safe_mkdir(directory=configuration.cliargs.prefix)
  for filename in os.listdir(configuration.cliargs.build_dir):
    if filename.endswith('.track_build'):
      is_program = False
      is_library = False
      track_file = configparser.ConfigParser()
      track_file.read(os.path.join(configuration.cliargs.build_dir, filename))
      if track_file.has_option(section='build', option='output'):
        output = track_file.get(section='build', option='output')
        if track_file.has_option(section='build', option='program'):
          is_program = track_file.get(section='build', option='program')
        if track_file.has_option(section='build', option='library'):
          is_library = track_file.get(section='build', option='library')
        if is_program:
          bin_path = os.path.join(configuration.cliargs.prefix, configuration.cliargs.bin)
          safe_mkdir(directory=bin_path)
          configuration.fobos.print_n('Install "' + output + '" in "' + bin_path + '"')
          shutil.copy(output, bin_path)
        if is_library:
          lib_path = os.path.join(configuration.cliargs.prefix, configuration.cliargs.lib)
          safe_mkdir(directory=lib_path)
          configuration.fobos.print_n('Install "' + output + '" in "' + lib_path + '"')
          shutil.copy(output, lib_path)
          if track_file.has_option(section='build', option='mod_file'):
            mod_file = track_file.get(section='build', option='mod_file')
            inc_path = os.path.join(configuration.cliargs.prefix, configuration.cliargs.include)
            safe_mkdir(directory=inc_path)
            configuration.fobos.print_n('Install "' + mod_file + '" in "' + inc_path + '"')
            shutil.copy(mod_file, inc_path)


def run_fobis_doctests(configuration):
  """
  Run FoBiS in build mode.

  Parameters
  ----------
  configuration : FoBiSConfig()
  """
  builder = Builder(cliargs=configuration.cliargs, print_n=configuration.print_b, print_w=configuration.print_r)
  pfiles = parse_files(configuration=configuration)
  dependency_hiearchy(builder=builder, pfiles=pfiles, print_w=configuration.print_r, force_compile=configuration.cliargs.force_compile)
  nomodlibs = build_nomodlibs(configuration=configuration, pfiles=pfiles, builder=builder)
  doctests, doctests_dirs = parse_doctests(configuration=configuration, pfiles=pfiles, builder=builder)
  for pfile in pfiles:
    doctests.append(pfile)
  dependency_hiearchy(builder=builder, pfiles=doctests, print_w=configuration.print_r, force_compile=configuration.cliargs.force_compile)
  test_doctests(configuration=configuration, doctests=doctests, pfiles=pfiles, nomodlibs=nomodlibs, builder=builder)
  if not configuration.cliargs.keep_volatile_doctests:
    for doc_dir in doctests_dirs:
      if os.path.isdir(doc_dir):
        shutil.rmtree(doc_dir)


def parse_files(configuration, src_dir=None, is_doctest=False):
  """
  Parse files and return the list of parsed files.

  Parameters
  ----------
  configuration : FoBiSConfig()
  src_dir: str
    root directory into which search; if omitted use configuration.cliargs.src

  Returns
  -------
  list
    list of ParsedFile() objects
  """
  pfiles = []
  if src_dir is not None:
    src = [src_dir]
  else:
    src = configuration.cliargs.src
  for src_dir in src:
    if configuration.cliargs.disable_recursive_search:
      for filename in os.listdir(src_dir):
        if any(os.path.splitext(os.path.basename(filename))[1] == ext for ext in configuration.cliargs.extensions):
          if (os.path.basename(filename) not in [os.path.basename(exc) for exc in configuration.cliargs.exclude] and
              all(exc not in os.path.dirname(filename) for exc in configuration.cliargs.exclude_dirs)):
             pfile = ParsedFile(name=os.path.join(src_dir, filename), is_doctest=is_doctest)
             if is_doctest:
               pfile.parse(inc=configuration.cliargs.inc, preprocessor=configuration.cliargs.doctests_preprocessor, preproc=configuration.cliargs.preproc, include=configuration.cliargs.include)
             else:
               pfile.parse(inc=configuration.cliargs.inc, preproc=configuration.cliargs.preproc, include=configuration.cliargs.include)
             pfiles.append(pfile)
    else:
      for root, _, files in os.walk(src_dir):
        for filename in files:
          if any(os.path.splitext(os.path.basename(filename))[1] == ext for ext in configuration.cliargs.extensions):
            if (os.path.basename(filename) not in [os.path.basename(exc) for exc in configuration.cliargs.exclude] and
                all(exc not in root for exc in configuration.cliargs.exclude_dirs)):
              filen = os.path.join(root, filename)
              pfile = ParsedFile(name=filen, is_doctest=is_doctest)
              if is_doctest:
                pfile.parse(inc=configuration.cliargs.inc, preprocessor=configuration.cliargs.doctests_preprocessor, preproc=configuration.cliargs.preproc, include=configuration.cliargs.include)
              else:
                pfile.parse(inc=configuration.cliargs.inc, preproc=configuration.cliargs.preproc, include=configuration.cliargs.include)
              pfiles.append(pfile)
  return pfiles


def parse_doctests(configuration, pfiles, builder):
  """Parse parsed-files for

  Parameters
  ----------
  configuration : FoBiSConfig()
  pfiles : list
    list of ParsedFile() objects
  builder : Builder()

  Returns
  -------
  list
    list of doctests
  """
  doctests = []
  doctests_dirs = []
  for pfile in pfiles:
    if pfile.doctest:
      if pfile.doctest.to_test:
        doc_dir = pfile.doctest.save_volatile_programs(build_dir=builder.build_dir)
        doctests_dirs.append(doc_dir)
  if len(doctests_dirs) > 0:
    doctests_dirs = list(set(doctests_dirs))
  for doc_dir in doctests_dirs:
    doctests += parse_files(configuration=configuration, src_dir=doc_dir, is_doctest=True)
  return doctests, doctests_dirs


def build_pfile(configuration, pfile, pfiles, nomodlibs, submodules, builder):
  """Build a parsed file.

  Parameters
  ----------
  configuration : FoBiSConfig()
  pfile : ParsedFile()
  pfiles : list
    list of ParsedFile() objects
  nomodlibs : list
    list of built non module libraries object names
  submodules : list
    list of built submodules object names
  builder : Builder()
  """
  configuration.print_b(builder.verbose(quiet=configuration.cliargs.quiet))
  if pfile.program:
    remove_other_main(builder=builder, pfiles=pfiles, myself=pfile)
  builder.build(file_to_build=pfile, output=configuration.cliargs.output, nomodlibs=nomodlibs, submodules=submodules, mklib=configuration.cliargs.mklib, verbose=configuration.cliargs.verbose, log=configuration.cliargs.log, track=configuration.cliargs.track_build)
  if configuration.cliargs.log:
    pfile.save_build_log(builder=builder)
  if configuration.cliargs.graph:
    pfile.save_dep_graph()


def build_nomodlibs(configuration, pfiles, builder):
  """Build all non module library files.

  Parameters
  ----------
  configuration : FoBiSConfig()
  pfiles : list
    list of ParsedFile() objects
  builder : Builder()

  Returns
  -------
  list
    list of built non module libraries object names
  """
  nomodlibs = []
  for pfile in pfiles:
    if pfile.nomodlib:
      build_ok = builder.build(file_to_build=pfile, verbose=configuration.cliargs.verbose, log=configuration.cliargs.log)
      if build_ok:
        nomodlibs = nomodlibs + pfile.obj_dependencies(exclude_programs=True)
  return nomodlibs


def build_submodules(configuration, pfiles, builder):
  """Build all submodule files.

  Parameters
  ----------
  configuration : FoBiSConfig()
  pfiles : list
    list of ParsedFile() objects
  builder : Builder()

  Returns
  -------
  list
    list of built submodules object names
  """
  submodules = []
  for pfile in pfiles:
    if pfile.submodule:
      build_ok = builder.build(file_to_build=pfile, verbose=configuration.cliargs.verbose, log=configuration.cliargs.log)
      if build_ok:
        submodules.append(pfile.basename + ".o")
  return submodules


def test_doctests(configuration, doctests, pfiles, nomodlibs, builder):
  """Test doctests: build/execute/check-result of each doctest.

  Parameters
  ----------
  configuration : FoBiSConfig()
  doctests : list
    list of ParsedFile() objects containing doctests
  pfiles : list
    list of ParsedFile() objects
  nomodlibs : list
    list of built non module libraries object names
  builder : Builder()
  """
  for test in doctests:
    if test.is_doctest and os.path.basename(test.name).split("-doctest")[0] not in [os.path.basename(os.path.splitext(exc)[0]) for exc in configuration.cliargs.exclude_from_doctests]:
      remove_other_main(builder=builder, pfiles=pfiles, myself=test)
      builder.build(file_to_build=test, nomodlibs=nomodlibs, verbose=False, log=False, quiet=True)
      test_exe = os.path.join(builder.build_dir, os.path.splitext(os.path.basename(test.name))[0])
      configuration.print_b('executing doctest ' + os.path.basename(test_exe))
      result = syswork(test_exe)
      if result[0] == 0:
        # comparing results
        test_result = os.path.join(os.path.dirname(test.name), os.path.splitext(os.path.basename(test.name))[0] + '.result')
        with open(test_result, 'r') as res:
          expected_result = res.read()
        if result[1].strip() == expected_result:
          configuration.print_b('doctest passed')
        else:
          configuration.print_r('doctest failed!')
          configuration.print_b('  result obtained: "' + result[1].strip() + '"')
          configuration.print_b('  result expected: "' + expected_result + '"')
      if not configuration.cliargs.keep_volatile_doctests:
        os.remove(test_exe)


def save_makefile(configuration, pfiles, builder):
  """
  Save GNU makefile.

  Parameters
  ----------
  pfiles : list
    list of parsed files
  builder : Builder object
  """
  def _gnu_variables(builder):
    """
    Method for getting GNU Make variables

    Parameters
    ----------
    builder : Builder object

    Returns
    -------
    str
      string containing the GNU Make variables
    """
    string = []
    string.append("\n#main building variables\n")
    string.append("DSRC    = " + " ".join(configuration.cliargs.src) + "\n")
    string.append(builder.gnu_make())
    string.append("VPATH   = $(DSRC) $(DOBJ) $(DMOD)" + "\n")
    string.append("MKDIRS  = $(DOBJ) $(DMOD) $(DEXE)" + "\n")
    string.append("LCEXES  = $(shell echo $(EXES) | tr '[:upper:]' '[:lower:]')\n")
    string.append("EXESPO  = $(addsuffix .o,$(LCEXES))\n")
    string.append("EXESOBJ = $(addprefix $(DOBJ),$(EXESPO))\n")
    string.append("\n")
    string.append("#auxiliary variables\n")
    string.append('COTEXT  = "Compiling $(<F)"\n')
    string.append('LITEXT  = "Assembling $@"\n')
    return "".join(string)

  def _gnu_building_rules(pfiles):
    """
    Method returing the building rules.

    Parameters
    ----------
    pfifles : list
      list of parsed file

    Returns
    -------
    str
      string containing the building rules
    """
    # collect non-module-libraries object
    nomodlibs = []
    for pfile in pfiles:
      if pfile.nomodlib:
        nomodlibs.append("$(DOBJ)" + pfile.basename.lower() + ".o")
    string = []
    string.append("\n#building rules\n")
    # linking rules
    for pfile in pfiles:
      save_target_rule = False
      if pfile.program:
        save_target_rule = True
      elif configuration.cliargs.target:
        if os.path.basename(configuration.cliargs.target) == os.path.basename(pfile.name):
          save_target_rule = True
      if save_target_rule:
        if len(nomodlibs) > 0:
          string.append("$(DEXE)" + pfile.basename.upper() + ": $(MKDIRS) " + "$(DOBJ)" + pfile.basename.lower() + ".o \\" + "\n")
          for nomod in nomodlibs[:-1]:
            string.append("\t" + nomod + " \\" + "\n")
          string.append("\t" + nomodlibs[-1] + "\n")
        else:
          string.append("$(DEXE)" + pfile.basename.upper() + ": $(MKDIRS) " + "$(DOBJ)" + pfile.basename.lower() + ".o\n")
        string.append("\t@rm -f $(filter-out $(DOBJ)" + pfile.basename.lower() + ".o,$(EXESOBJ))\n")
        string.append("\t@echo $(LITEXT)\n")
        string.append("\t@$(FC) $(OPTSL) $(DOBJ)*.o $(LIBS) -o $@\n")
        string.append("EXES := $(EXES) " + pfile.basename.upper() + "\n")
    return "".join(string)

  def _gnu_auxiliary_rules():
    """
    Method returing some useful GNU Make auxiliary rules

    Returns
    -------
    str
      string containing the auxiliary rules
    """
    string = []
    string.append("#phony auxiliary rules\n")
    string.append(".PHONY : $(MKDIRS)\n")
    string.append("$(MKDIRS):\n")
    string.append("\t@mkdir -p $@\n")
    string.append(".PHONY : cleanobj\n")
    string.append("cleanobj:\n")
    string.append("\t@echo deleting objects\n")
    string.append("\t@rm -fr $(DOBJ)\n")
    string.append(".PHONY : cleanmod\n")
    string.append("cleanmod:\n")
    string.append("\t@echo deleting mods\n")
    string.append("\t@rm -fr $(DMOD)\n")
    string.append(".PHONY : cleanexe\n")
    string.append("cleanexe:\n")
    string.append("\t@echo deleting exes\n")
    string.append("\t@rm -f $(addprefix $(DEXE),$(EXES))\n")
    string.append(".PHONY : clean\n")
    string.append("clean: cleanobj cleanmod\n")
    string.append(".PHONY : cleanall\n")
    string.append("cleanall: clean cleanexe\n")
    return "".join(string)

  string = []
  string.append("#!/usr/bin/make\n")
  string.append(_gnu_variables(builder=builder))
  string.append(_gnu_building_rules(pfiles=pfiles))
  string.append("\n#compiling rules\n")
  for pfile in pfiles:
    string.append(pfile.gnu_make_rule(builder=builder))
  string.append(_gnu_auxiliary_rules())
  with open(configuration.cliargs.makefile, "w") as mk_file:
    mk_file.writelines(string)


def gcov_analyzer(configuration):
  """
  Run gcov file analyzer.
  """
  gcovs = []
  for root, _, files in os.walk('.'):
    for filename in files:
      if os.path.splitext(os.path.basename(filename))[1] == '.gcov':
        configuration.print_b('Analyzing ' + os.path.join(root, filename))
        gcovs.append(Gcov(filename=os.path.join(root, filename)))
  for gcov in gcovs:
    gcov.parse()
    gcov.save(output=os.path.join(configuration.cliargs.gcov_analyzer[0], os.path.basename(gcov.filename) + '.md'), graphs=True)
  if len(gcovs) > 0 and len(configuration.cliargs.gcov_analyzer) > 1:
    string = []
    string.append('### ' + configuration.cliargs.gcov_analyzer[1] + '\n')
    for gcov in gcovs:
      string.append('\n#### [[' + os.path.basename(gcov.filename) + ']]\n\n')
      string.append(gcov.l_pie_url + '\n' + gcov.p_pie_url + '\n')
    with open(os.path.join(configuration.cliargs.gcov_analyzer[0], configuration.cliargs.gcov_analyzer[1] + '.md'), 'w') as summary:
      summary.writelines(string)


def is_ascii_kind_supported(configuration):
  """Check is the compiler support ASCII character kind.

  Parameters
  ----------
  configuration : FoBiSConfig()


  Returns
  -------
  bool
    true if ASCII kind is supported, false otherwise
  """
  builder = Builder(cliargs=configuration.cliargs, print_n=configuration.print_b, print_w=configuration.print_r)
  test_file_name = os.path.join(builder.build_dir, 'ascii_kind_introspection.f90')
  test = open(test_file_name, 'w')
  test.write("program test\nprint*, selected_char_kind('ascii')\nendprogram")
  test.close()
  test = ParsedFile(name=test_file_name)
  test.parse(inc=configuration.cliargs.inc)
  pfiles = [test]
  dependency_hiearchy(builder=builder, pfiles=pfiles, print_w=configuration.print_r)
  builder.build(file_to_build=pfiles[0], verbose=configuration.cliargs.verbose, log=configuration.cliargs.log)
  os.remove(test_file_name)
  test_exe = os.path.join(builder.build_dir, os.path.splitext(os.path.basename(test.name))[0])
  result = syswork(test_exe)
  os.remove(test_exe)
  is_supported = False
  if result[0] == 0:
    if int(result[1]) > 0:
      is_supported = True
  print("Compiler '" + builder.compiler.compiler + "' support ASCII kind:", is_supported)
  return is_supported


def is_ucs4_kind_supported(configuration):
  """Check is the compiler support UCS4 character kind.

  Parameters
  ----------
  configuration : FoBiSConfig()


  Returns
  -------
  bool
    true if UCS4 kind is supported, false otherwise
  """
  builder = Builder(cliargs=configuration.cliargs, print_n=configuration.print_b, print_w=configuration.print_r)
  test_file_name = os.path.join(builder.build_dir, 'ucs4_kind_introspection.f90')
  test = open(test_file_name, 'w')
  test.write("program test\nprint*, selected_char_kind('iso_10646')\nendprogram")
  test.close()
  test = ParsedFile(name=test_file_name)
  test.parse(inc=configuration.cliargs.inc)
  pfiles = [test]
  dependency_hiearchy(builder=builder, pfiles=pfiles, print_w=configuration.print_r)
  builder.build(file_to_build=pfiles[0], verbose=configuration.cliargs.verbose, log=configuration.cliargs.log)
  os.remove(test_file_name)
  test_exe = os.path.join(builder.build_dir, os.path.splitext(os.path.basename(test.name))[0])
  result = syswork(test_exe)
  os.remove(test_exe)
  is_supported = False
  if result[0] == 0:
    if int(result[1]) > 0:
      is_supported = True
  print("Compiler '" + builder.compiler.compiler + "' support UCS4 kind:", is_supported)
  return is_supported


def is_float128_kind_supported(configuration):
  """Check is the compiler support float128 real kind.

  Parameters
  ----------
  configuration : FoBiSConfig()


  Returns
  -------
  bool
    true if UCS4 kind is supported, false otherwise
  """
  builder = Builder(cliargs=configuration.cliargs, print_n=configuration.print_b, print_w=configuration.print_r)
  test_file_name = os.path.join(builder.build_dir, 'float128_kind_introspection.f90')
  test = open(test_file_name, 'w')
  test.write("program test\nprint*, selected_real_kind(33,4931)\nendprogram")
  test.close()
  test = ParsedFile(name=test_file_name)
  test.parse(inc=configuration.cliargs.inc)
  pfiles = [test]
  dependency_hiearchy(builder=builder, pfiles=pfiles, print_w=configuration.print_r)
  builder.build(file_to_build=pfiles[0], verbose=configuration.cliargs.verbose, log=configuration.cliargs.log)
  os.remove(test_file_name)
  test_exe = os.path.join(builder.build_dir, os.path.splitext(os.path.basename(test.name))[0])
  result = syswork(test_exe)
  os.remove(test_exe)
  is_supported = False
  if result[0] == 0:
    if int(result[1]) > 0:
      is_supported = True
  print("Compiler '" + builder.compiler.compiler + "' support float128 kind:", is_supported)
  return is_supported

if __name__ == '__main__':
  main()
