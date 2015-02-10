#!/usr/bin/env python
"""
ParsedFile.py, module definition of Dependency class.
This is a class designed for handling a single parsed file.
"""
import os
import re
import sys
from .config import __config__
from .Dependency import Dependency
from .utils import traverse_recursive
from .utils import unique_seq
# definition of regular expressions
__str_f95_apex__ = r"('|" + r'")'
__str_f95_kw_include__ = r"[Ii][Nn][Cc][Ll][Uu][Dd][Ee]"
__str_f95_kw_intrinsic__ = r"[Ii][Nn][Tt][Rr][Ii][Nn][Ss][Ii][Cc]"
__str_f95_kw_module__ = r"[Mm][Oo][Dd][Uu][Ll][Ee]"
__str_f95_kw_program__ = r"[Pp][Rr][Oo][Gg][Rr][Aa][Mm]"
__str_f95_kw_use__ = r"[Uu][Ss][Ee]"
__str_f95_kw_mpifh__ = r"[Mm][Pp][Ii][Ff]\.[Hh]"
__str_f95_name__ = r"(?P<name>[a-zA-Z][a-zA-Z0-9_]*)"
__str_f95_eol__ = r"(?P<eol>\s*!.*|\s*)?$"
__str_f95_mod_rename__ = r"(\s*,\s*[a-zA-Z][a-zA-Z0-9_]*\s*=>\s*[a-zA-Z][a-zA-Z0-9_]*)*"
__str_f95_mod_only__ = r"(\s*,\s*[Oo][Nn][Ll][Yy]\s*:\s*([a-zA-Z][a-zA-Z0-9_]*\s*=>\s*[a-zA-Z][a-zA-Z0-9_]*|[a-zA-Z][a-zA-Z0-9_]*))*"
__str_f95_use_mod__ = (r"^(\s*)" +  # eventual initial white spaces
                       __str_f95_kw_use__ +  # f95 keyword "use"
                       r"(\s+)" +  # 1 or more white spaces
                       __str_f95_name__ +  # f95 construct name
                       r"(?P<mod_eol>(.*))")
__str_f95_include__ = (r"^(\s*|\#)" +  # eventual initial white spaces or "#" character
                       __str_f95_kw_include__ +  # f95 keyword "include"
                       r"(\s+)" +  # 1 or more white spaces
                       __str_f95_apex__ +  # character "'" or '"'
                       r"(\s*)" +  # eventaul white spaces
                       r"(?P<name>.*)" +  # name of included file
                       r"(\s*)" +  # eventaul white spaces
                       __str_f95_apex__ +  # character "'" or '"'
                       __str_f95_eol__)  # eventual eol white space and or comment
__str_f95_module__ = (r"^(\s*)" +  # eventual initial white spaces
                      r"(?P<scplevel>" + __str_f95_kw_module__ + r")" +  # f95 keyword "module"
                      r"(\s+)" +  # 1 or more white spaces
                      __str_f95_name__ +  # f95 construct name
                      __str_f95_eol__)  # eventual eol white space and or comment
__str_f95_program__ = (r"^(\s*)" +  # eventual initial white spaces
                       r"(?P<scplevel>" + __str_f95_kw_program__ + r")" +  # f95 keyword "program"
                       r"(\s+)" +  # 1 or more white spaces
                       __str_f95_name__ +  # f95 construct name
                       __str_f95_eol__)  # eventual eol white space and or comment
__str_f95_intrinsic__ = (r"(,\s*)" + __str_f95_kw_intrinsic__ + r"(\s+)")
__str_f95_mpifh__ = (r"(.*)" + __str_f95_kw_mpifh__ + r"(.*)")
__regex_f95_use_mod__ = re.compile(__str_f95_use_mod__)
__regex_f95_include__ = re.compile(__str_f95_include__)
__regex_f95_program__ = re.compile(__str_f95_program__)
__regex_f95_module__ = re.compile(__str_f95_module__)
__regex_f95_intrinsic__ = re.compile(__str_f95_intrinsic__)
__regex_f95_mpifh__ = re.compile(__str_f95_mpifh__)


class ParsedFile(object):
  """ParsedFile is an object that handles a single parsed file, its attributes and methods."""
  def __init__(self,
               name,
               program=False,
               module=False,
               include=False,
               nomodlib=False,
               to_compile=False,
               output=None):
    """
    Parameters
    ----------
    name : str
      file name
    program : {False}
      flag for tagging program file
    module : {False}
      flag for tagging module file
    include : {False}
      flag for tagging include file
    nomodlib : {False}
      flag for tagging library of procedures without an enclosing module (old Fortran style)
    to_compile : {False}
      flag for tagging file to be compiled
    output : {None}
      string of output file name

    Attributes
    ----------
    name : str
      file name
    program : bool
      flag for tagging program file
    module : bool
      flag for tagging module file
    include : bool
      flag for tagging include file
    nomodlib : bool
      flag for tagging library of procedures without an enclosing module (old Fortran style)
    to_compile : bool
      flag for tagging file to be compiled
    output : str
      string of output file name
    basename : str
      basename of file name
    extension : str
      extension of file name
    timestamp : str
      timestamp of file
    order :
    pfile_dep : list
      list of parsed file dependencies
    """
    self.name = name
    self.program = program
    self.module = module
    self.include = include
    self.nomodlib = nomodlib
    self.to_compile = to_compile
    self.output = output
    self.basename = os.path.splitext(os.path.basename(self.name))[0]
    self.extension = os.path.splitext(os.path.basename(self.name))[1]
    self.timestamp = os.path.getmtime(self.name)
    self.order = 0
    self.pfile_dep = None
    self.pfile_dep_all = None
    self.module_names = None
    self.dependencies = None

  def parse(self):
    """
    The method parse parses the file creating its the dependencies list and the list of modules names that self eventually contains.
    """
    self.module_names = []
    self.dependencies = []
    ffile = open(self.name, "r")
    for line in ffile:
      matching = re.match(__regex_f95_program__, line)
      if matching:
        self.program = True
      matching = re.match(__regex_f95_module__, line)
      if matching:
        self.module = True
        self.module_names.append(matching.group('name'))
      matching = re.match(__regex_f95_use_mod__, line)
      if matching:
        if not re.match(__regex_f95_intrinsic__, line):
          if matching.group('name').lower() != 'mpi' and matching.group('name').lower() != 'omp_lib':
            dep = Dependency(dtype="module", name=matching.group('name'))
            self.dependencies.append(dep)
      matching = re.match(__regex_f95_include__, line)
      if matching:
        if not re.match(__regex_f95_mpifh__, line):
          dep = Dependency(dtype="include", name=matching.group('name'))
          self.dependencies.append(dep)
    ffile.close()
    if not self.program and not self.module:
      if os.path.splitext(os.path.basename(self.name))[1] not in __config__.extensions_inc:
        self.nomodlib = True

  def save_build_log(self, builder):
    """
    The method save_build_log save a log file containing information about the building options used.
    """
    log_file = open("build_" + self.basename + ".log", "w")
    log_file.writelines("Hierarchical dependencies list of: " + self.name + "\n")
    for dep in self.pfile_dep:
      log_file.writelines("  " + dep.name + "\n")
      log_file.writelines(dep.str_dependencies(pref="    "))
    log_file.writelines("Complete ordered dependencies list of: " + self.name + "\n")
    for dep in self.pfile_dep_all:
      log_file.writelines("  " + dep.name + "\n")
    log_file.writelines(builder.verbose())
    log_file.close()

  def save_makefile(self, makefile, builder):
    """
    The method save_makefile save a minimal makefile for building the file by means of GNU Make.
    """
    if not self.include:
      mk_file = open(makefile, "a")
      file_dep = [self.name]
      for dep in self.pfile_dep:
        if dep.include:
          file_dep.append(dep.name)
      if (len(self.pfile_dep) - len(file_dep)) >= 0:
        mk_file.writelines("$(DOBJ)" + self.basename.lower() + ".o:" + "".join([" " + f for f in file_dep]) + " \\" + "\n")
        for dep in self.pfile_dep[:-1]:
          if not dep.include:
            mk_file.writelines("\t$(DOBJ)" + os.path.splitext(os.path.basename(dep.name))[0].lower() + ".o \\" + "\n")
        if not self.pfile_dep[-1].include:
          mk_file.writelines("\t$(DOBJ)" + os.path.splitext(os.path.basename(self.pfile_dep[-1].name))[0].lower() + ".o\n")
      else:
        mk_file.writelines("$(DOBJ)" + self.basename.lower() + ".o:" + "".join([" " + f for f in file_dep]) + "\n")
      mk_file.writelines("\t@echo $(COTEXT)\n")
      mk_file.writelines("\t@$(FC) $(OPTSC) $(PREPROC) " + ''.join(['-I' + i + ' ' for i in builder.dinc]) + " $< -o $@\n")
      mk_file.writelines("\n")
      mk_file.close()
    return

  def str_dependencies(self,
                       pref=""):  # prefixing string
    """
    The method str_dependencies create a string containing the depencies files list.
    """
    str_dep = ""
    for dep in self.pfile_dep:
      str_dep = str_dep + pref + dep.name + "\n"
    return str_dep

  def obj_dependencies(self, exclude_programs=False):
    """
    The method obj_dependencies create a list containing the dependencies object files list.

    Parameters
    ----------
    exclude_programs : {False}
      flag for excluding programs obj from the list
    """
    if exclude_programs:
      return [p.basename + ".o" for p in self.pfile_dep_all if not p.include and not p.program]
    else:
      return [p.basename + ".o" for p in self.pfile_dep_all if not p.include]

  def check_compile(self, obj_dir, force_compile=False):
    """
    The method check_compile checks if self must be compiled.

    Parameters
    ----------
    obj_dir : str
      directory where compiled objects are saved
    force_compile : {False}
      flag for forcing (re-)compiling of all dependency
    """
    if not self.include:
      # verifying if dependencies are up-to-date
      for dep in self.pfile_dep_all:
        if not dep.include:
          if force_compile:
            self.to_compile = True
          else:
            obj = obj_dir + dep.basename + ".o"
            # verifying if dep is up-to-date
            if os.path.exists(obj):
              if os.path.getmtime(obj) < dep.timestamp:
                # found a dependency object that is out-of-date, thus self (and dep) must be compiled
                self.to_compile = True
            else:
              # compiled object of a dependency is absent, thus self must be compiled
              self.to_compile = True
        else:
          # verifying if dep is newer than self
          if not os.path.exists(dep.name):
            print(" Attention: file " + dep.name + " does not exist, but it is a dependency of file " + self.name)
            sys.exit(1)
          else:
            # comparing the include dependency with the self-compiled-object if exist
            obj = obj_dir + self.basename + ".o"
            # verifying if dep is up-to-date
            if os.path.exists(obj):
              if os.path.getmtime(obj) < os.path.getmtime(dep.name):
                # found an include that is newer than self-compiled-object, thus self must be compiled
                self.to_compile = True
      # verifying if self is up-to-date
      if not self.to_compile:
        obj = obj_dir + self.basename + ".o"
        if os.path.exists(obj):
          if os.path.getmtime(obj) < self.timestamp:
            # the compiled object is out-of-date, thus self must be compiled
            self.to_compile = True
        else:
          # compiled object is absent, thus self must be compiled
          self.to_compile = True

  def create_pfile_dep_all(self):
    """
    The method create_pfile_dep_all create a complete list of all dependencies direct and indirect.
    """
    self.pfile_dep_all = []
    for path in traverse_recursive(self):
      self.pfile_dep_all.append(path[-1])
    self.pfile_dep_all = unique_seq(self.pfile_dep_all)
    return
