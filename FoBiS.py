#!/usr/bin/env python
"""
FoBiS.py, Fortran Building System for poor men
"""
__appname__ = 'FoBiS.py'
__version__ ="0.0.1"
__author__  = 'Stefano Zaghi'
# modules loading
import sys
try:
  import os
except:
  print "Module 'os' not found"
  sys.exit(1)
try:
  import time
except:
  print "Module 'time' not found"
  sys.exit(1)
try:
  import argparse
except:
  print "Module 'argparse' not found"
  sys.exit(1)
try:
  from copy import deepcopy
except:
  print "Module 'copy' not found"
  sys.exit(1)
try:
  import subprocess
except:
  print "Module 'subprocess' not found"
  sys.exit(1)
try:
  import shutil
except:
  print "Module 'shutil' not found"
  sys.exit(1)
try:
  import ConfigParser
except:
  print "Module 'ConfigParser' not found"
  sys.exit(1)
try:
  import operator
except:
  print "Module 'operator' not found"
  sys.exit(1)
try:
  import re
except:
  print "The regular expression module 're' not found"
  sys.exit(1)
try:
  from multiprocessing import Pool
  parallel=True
except:
  print "Module 'multiprocessing' not found: parallel compilation disabled"
  parallel=False
# setting CLI
cliparser = argparse.ArgumentParser(prog=__appname__,description='FoBiS.py, Fortran Building System for poor men')
cliparser.add_argument('-v','--version',action='version',help='Show version',version='%(prog)s '+__version__)
clisubparsers = cliparser.add_subparsers(title='Commands',description='Valid commands')
buildparser = clisubparsers.add_parser('build',help='Build all programs found or a specific target')
buildparser.set_defaults(which='build')
cleanparser = clisubparsers.add_parser('clean',help='Clean project: completely remove OBJ and MOD directories... use carefully')
cleanparser.set_defaults(which='clean')
rulexparser = clisubparsers.add_parser('rule', help='Execute rules defined into a fobos file')
rulexparser.set_defaults(which='rule')
buildparser.add_argument('-f',       '--fobos',    required=False,action='store',               default=None,            help='Specify a "fobos" file named differently from "fobos"')
buildparser.add_argument('-colors',                required=False,action='store_true',          default=False,           help='Activate colors in shell prints [default: no colors]')
buildparser.add_argument('-l',       '--log',      required=False,action='store_true',          default=False,           help='Activate the creation of a log file [default: no log file]')
buildparser.add_argument('-q',       '--quiet',    required=False,action='store_true',          default=False,           help='Less verbose than default')
buildparser.add_argument('-j',       '--jobs',     required=False,action='store',               default=1,      type=int,help='Specify the number of concurrent jobs used for compiling dependencies [default 1]')
buildparser.add_argument('-compiler',              required=False,action='store',               default='Intel',         help='Compiler used: Intel, GNU, IBM, PGI, g95 or Custom [default: Intel]')
buildparser.add_argument('-fc',                    required=False,action='store',               default='',              help='Specify the Fortran compiler statement, necessary for custom compiler specification (-compiler Custom)')
buildparser.add_argument('-modsw',                 required=False,action='store',               default='',              help='Specify the switch for setting the module searching path, necessary for custom compiler specification (-compiler Custom)')
buildparser.add_argument('-mpi',                   required=False,action='store_true',          default=False,           help='Use MPI enabled version of compiler')
buildparser.add_argument('-cflags',                required=False,action='store',               default='',              help='Compile flags')
buildparser.add_argument('-lflags',                required=False,action='store',               default='',              help='Link flags')
buildparser.add_argument('-libs',                  required=False,action='store',     nargs='+',default=[],              help='List of external libraries used')
buildparser.add_argument('-i',       '--include',  required=False,action='store',     nargs='+',default=[],              help='List of directories for searching included files')
buildparser.add_argument('-inc',                   required=False,action='store',     nargs='+',default=[],              help='Add a list of custom-defined file extensions for include files')
buildparser.add_argument('-p',       '--preproc',  required=False,action='store',               default='',              help='Preprocessor flags')
buildparser.add_argument('-dobj',    '--obj_dir',  required=False,action='store',               default='./obj/',        help='Directory containing compiled objects [default: ./obj/]')
buildparser.add_argument('-dmod',    '--mod_dir',  required=False,action='store',               default='./mod/',        help='Directory containing .mod files of compiled objects [default: ./mod/]')
buildparser.add_argument('-dbld',    '--build_dir',required=False,action='store',               default='./',            help='Directory containing executable objects [default: ./]')
buildparser.add_argument('-s',       '--src',      required=False,action='store',               default='./',            help='Root-directory of source files [default: ./]')
buildparser.add_argument('-e',       '--exclude',  required=False,action='store',     nargs='+',default=[],              help='Exclude a list of files from the building process')
buildparser.add_argument('-t',       '--target',   required=False,action='store',               default=None,            help='Specify a target file [default: all programs found]')
buildparser.add_argument('-o',       '--output',   required=False,action='store',               default=None,            help='Specify the output file name is used with -target switch [default: basename of target]')
buildparser.add_argument('-mklib',                 required=False,action='store',               default=None,            help='Build library instead of program (use with -target switch); usage: -mklib static or -mklib shared')
buildparser.add_argument('-mode',                  required=False,action='store',               default=None,            help='Select a mode defined into a fobos file')
buildparser.add_argument('-lmodes',                required=False,action='store_true',          default=False,           help='List the modes defined into a fobos file')
buildparser.add_argument('-m',       '--makefile', required=False,action='store_true',          default=False,           help='Generate a GNU Makefile for building the project')
cleanparser.add_argument('-f',       '--fobos',    required=False,action='store',               default=None,            help='Specify a "fobos" file named differently from "fobos"')
cleanparser.add_argument('-colors',                required=False,action='store_true',          default=False,           help='Activate colors in shell prints [default: no colors]')
cleanparser.add_argument('-dobj',    '--obj_dir',  required=False,action='store',               default='./obj/',        help='Directory containing compiled objects [default: ./obj/]')
cleanparser.add_argument('-dmod',    '--mod_dir',  required=False,action='store',               default='./mod/',        help='Directory containing .mod files of compiled objects [default: ./mod/]')
cleanparser.add_argument('-dbld',    '--build_dir',required=False,action='store',               default='./',            help='Directory containing executable objects [default: ./]')
cleanparser.add_argument('-t',       '--target',   required=False,action='store',               default=None,            help='Specify a target file [default: all programs found]')
cleanparser.add_argument('-o',       '--output',   required=False,action='store',               default=None,            help='Specify the output file name is used with -target switch [default: basename of target]')
cleanparser.add_argument('-only_obj',              required=False,action='store_true',          default=False,           help='Clean only compiled objects and not also built targets')
cleanparser.add_argument('-only_target',           required=False,action='store_true',          default=False,           help='Clean only built targets and not also compiled objects')
cleanparser.add_argument('-mklib',                 required=False,action='store',               default=None,            help='Build library instead of program (use with -target switch); usage: -mklib static or -mklib shared')
cleanparser.add_argument('-mode',                  required=False,action='store',               default=None,            help='Select a mode defined into a fobos file')
cleanparser.add_argument('-lmodes',                required=False,action='store_true',          default=False,           help='List the modes defined into a fobos file')
rulexparser.add_argument('-f',       '--fobos',    required=False,action='store',               default=None,            help='Specify a "fobos" file named differently from "fobos"')
rulexparser.add_argument('-ex',      '--execute',  required=False,action='store',               default=None,            help='Specify a rule (defined into fobos file) to be executed', metavar='RULE')
rulexparser.add_argument('-ls',      '--list',     required=False,action='store_true',          default=False,           help='List the rules defined into a fobos file')
# definition of regular expressions
str_f95_apex         = r"('|"+r'")'
str_f95_kw_include   = r"[Ii][Nn][Cc][Ll][Uu][Dd][Ee]"
str_f95_kw_intrinsic = r"[Ii][Nn][Tt][Rr][Ii][Nn][Ss][Ii][Cc]"
str_f95_kw_module    = r"[Mm][Oo][Dd][Uu][Ll][Ee]"
str_f95_kw_program   = r"[Pp][Rr][Oo][Gg][Rr][Aa][Mm]"
str_f95_kw_use       = r"[Uu][Ss][Ee]"
str_f95_kw_mpifh     = r"[Mm][Pp][Ii][Ff]\.[Hh]"
str_f95_name         = r"(?P<name>[a-zA-Z][a-zA-Z0-9_]*)"
str_f95_eol          = r"(?P<eol>\s*!.*|\s*)?$"
str_f95_mod_rename   = r"(\s*,\s*[a-zA-Z][a-zA-Z0-9_]*\s*=>\s*[a-zA-Z][a-zA-Z0-9_]*)*"
str_f95_mod_only     = r"(\s*,\s*[Oo][Nn][Ll][Yy]\s*:\s*([a-zA-Z][a-zA-Z0-9_]*\s*=>\s*[a-zA-Z][a-zA-Z0-9_]*|[a-zA-Z][a-zA-Z0-9_]*))*"
str_f95_use_mod      = (r"^(\s*)"          + # eventual initial white spaces
                        str_f95_kw_use     + # f95 keyword "use"
                        r"(\s+)"           + # 1 or more white spaces
                        str_f95_name       + # f95 construct name
                        r"(?P<mod_eol>(.*))")
str_f95_include      = (r"^(\s*|\#)"       + # eventual initial white spaces or "#" character
                        str_f95_kw_include + # f95 keyword "include"
                        r"(\s+)"           + # 1 or more white spaces
                        str_f95_apex       + # character "'" or '"'
                        r"(\s*)"           + # eventaul white spaces
                        r"(?P<name>.*)"    + # name of included file
                        r"(\s*)"           + # eventaul white spaces
                        str_f95_apex       + # character "'" or '"'
                        str_f95_eol)         # eventual eol white space and or comment
str_f95_module       = (r"^(\s*)"                               + # eventual initial white spaces
                        r"(?P<scplevel>"+str_f95_kw_module+r")" + # f95 keyword "module"
                        r"(\s+)"                                + # 1 or more white spaces
                        str_f95_name                            + # f95 construct name
                        str_f95_eol)                              # eventual eol white space and or comment
str_f95_program      = (r"^(\s*)"                                + # eventual initial white spaces
                        r"(?P<scplevel>"+str_f95_kw_program+r")" + # f95 keyword "program"
                        r"(\s+)"                                 + # 1 or more white spaces
                        str_f95_name                             + # f95 construct name
                        str_f95_eol)                               # eventual eol white space and or comment
str_f95_intrinsic    = (r"(,\s*)"+str_f95_kw_intrinsic+r"(\s+)")
str_f95_mpifh        = (r"(.*)"+str_f95_kw_mpifh+r"(.*)")
regex_f95_use_mod    = re.compile(str_f95_use_mod)
regex_f95_include    = re.compile(str_f95_include)
regex_f95_program    = re.compile(str_f95_program)
regex_f95_module     = re.compile(str_f95_module)
regex_f95_intrinsic  = re.compile(str_f95_intrinsic)
regex_f95_mpifh      = re.compile(str_f95_mpifh)
__extensions_old__    = [".f",".F",".for",".FOR",".fpp",".FPP",".fortran",".f77",".F77"]
__extensions_modern__ = [".f90",".F90",".f95",".F95",".f03",".F03",".f08",".F08",".f2k",".F2K"]
__extensions_inc__    = [".inc",".INC",".h",".H"]
__extensions_parsed__ = __extensions_old__ + __extensions_modern__ + __extensions_inc__
# system worker function
def syswork(cmd):
  """
  Function for executing system command 'cmd': for compiling and linking files.
  """
  try:
    output = subprocess.check_output(cmd, shell=True)
    if output:
      print output
  except subprocess.CalledProcessError as err:
    if err.returncode != 0:
      sys.exit(1)
  return
# classes definitions
class Colors(object):
  """
  Colors is an object that handles colors of shell prints, its attributes and methods.
  """
  def __init__(self,
               red = '\033[1;31m',
               bld = '\033[1m'):
    self.red = red
    self.bld = bld
    self.end = '\033[0m'
  def disable(self):
    self.red = ''
    self.bld = ''
    self.end = ''
class Builder(object):
  """
  Builder is an object that handles the building system, its attributes and methods.
  """
  def __init__(self,
               compiler  = "Intel", # compiler used
               fc        = "",      # custom compiler statement
               modsw     = "",      # custom compiler switch for modules searching path
               mpi       = False,   # use MPI enabled version of compiler
               cflags    = "-c",    # compilation flags
               lflags    = "",      # linking flags
               libs      = [],      # list of external libraries
               dinc      = [],      # list of directories for searching included files
               preproc   = "",      # preprocessor flags
               build_dir = "./",    # directory containing built files
               mod_dir   = "./",    # directory containing .mod files
               obj_dir   = "./",    # directory containing compiled object files
               quiet     = False,   # make printings less verbose than default
               colors    = False,   # make printings colored
               jobs      = 1):      # concurrent compiling jobs
    self.compiler  = compiler
    self.fc        = fc
    self.modsw     = modsw
    self.mpi       = mpi
    self.cflags    = cflags
    self.lflags    = lflags
    self.libs      = libs
    self.dinc      = dinc
    self.preproc   = preproc
    self.build_dir = build_dir
    self.mod_dir   = build_dir+mod_dir
    self.obj_dir   = build_dir+obj_dir
    self.quiet     = quiet
    self.jobs      = jobs
    self.colors    = Colors()
    if not colors:
      self.colors.disable()
    if mpi:
      self.fc = 'mpif90'
    if compiler.lower() == 'gnu':
      if not mpi:
        self.fc = 'gfortran'
      self.modsw = '-J'
    elif compiler.lower() == 'intel':
      if not mpi:
        self.fc = 'ifort'
      self.modsw = '-module'
    elif compiler.lower() == 'g95':
      if not mpi:
        self.fc = 'g95'
      self.modsw = '-fmod='
    elif compiler.lower() == 'custom':
      pass # all is set from CLI
    if self.modsw[-1]!='=': # check necessary for g95 CLI trapping error
      self.modsw += ' '
    self.cmd_comp = self.fc+' '+self.cflags+' '+self.modsw+self.mod_dir+' '+self.preproc
    self.cmd_link = self.fc+' '+self.lflags+' '+self.modsw+self.mod_dir
    # checking paths integrity
    if not os.path.exists(self.mod_dir):
      os.makedirs(self.mod_dir)
    if not os.path.exists(self.obj_dir):
      os.makedirs(self.obj_dir)
    if not os.path.exists(self.build_dir):
      os.makedirs(self.build_dir)
  def compile_command(self,pfile):
    """
    The method compile_command returns the OS command for compiling pfile.
    """
    if len(self.dinc)>0:
      comp_cmd = self.cmd_comp+' '+''.join(['-I'+s+' ' for s in self.dinc])+pfile.name+' -o '+self.obj_dir+pfile.basename+'.o'
    else:
      comp_cmd = self.cmd_comp+' '                                         +pfile.name+' -o '+self.obj_dir+pfile.basename+'.o'
    return comp_cmd
  def build(self,pfile,output=None,nomodlibs=[],mklib=None):
    """
    The method build builds current file.
    """
    print self.colors.bld+'Building '+pfile.name+self.colors.end
    # correct the list ordering accordingly to indirect dependency
    for n,dep in enumerate(pfile.pfile_dep_all):
      for other_dep in pfile.pfile_dep_all:
        if other_dep != dep:
          if dep in other_dep.pfile_dep_all:
            dep.order+=1
    pfile.pfile_dep_all.sort(key=operator.attrgetter('order'),reverse=True)
    # creating a hierarchy list of compiling commands accordingly to the order of all dependencies
    if len([p for p in pfile.pfile_dep_all if not p.include and p.to_compile])>0:
      order_max = max([p for p in pfile.pfile_dep_all if not p.include and p.to_compile],key=operator.attrgetter('order')).order + 1
      hierarchy = [[] for i in range(order_max)]
      for dep in pfile.pfile_dep_all:
        if dep.to_compile and not dep.include:
          hierarchy[dep.order].append([dep.name,self.compile_command(pfile=dep)])
          dep.to_compile = False
      hierarchy = [h for h in hierarchy if len(h)>0]
      for deps in reversed(hierarchy):
        files = ''
        cmds = []
        for dep in deps:
          files = files+" "+dep[0]
          cmds.append(dep[1])
        if len(deps)>1 and self.jobs>1 and parallel:
          jobs = min(len(deps),self.jobs)
          print self.colors.bld+"Compiling"+files+" using "+str(jobs)+" concurrent processes"+self.colors.end
          pool = Pool(processes=jobs)
          pool.map(syswork,cmds)
          pool.close()
          pool.join()
        else:
          print self.colors.bld+"Compiling"+files+" serially "+self.colors.end
          for cmd in cmds:
            syswork(cmd)
    else:
      print self.colors.bld+'Nothing to compile, all objects are up-to-date'+self.colors.end
    if pfile.program:
      objs = nomodlibs + pfile.obj_dependencies()
      if output:
        exe=self.build_dir+output
      else:
        exe=self.build_dir+pfile.basename
      link_cmd = self.cmd_link+" "+"".join([self.obj_dir+s+" " for s in objs])+"".join([s+" " for s in self.libs])+"-o "+exe
      print self.colors.bld+"Linking "+exe+self.colors.end
      syswork(link_cmd)
      print self.colors.bld+'Target '+pfile.name+' has been successfully built'+self.colors.end
    elif mklib:
      if output:
        lib=self.build_dir+output
      else:
        if mklib.lower()=='shared':
          lib=self.build_dir+pfile.basename+'.so'
        elif mklib.lower()=='static':
          lib=self.build_dir+pfile.basename+'.a'
      if mklib.lower()=='shared':
        link_cmd = self.cmd_link+" "+"".join([s+" " for s in self.libs])+self.obj_dir+pfile.basename+".o -o "+lib
      elif mklib.lower()=='static':
        link_cmd = "ar -rcs "+lib+" "+self.obj_dir+pfile.basename+".o ; ranlib "+lib
      print self.colors.bld+"Linking "+lib+self.colors.end
      syswork(link_cmd)
      print self.colors.bld+'Target '+pfile.name+' has been successfully built'+self.colors.end
  def verbose(self):
    """
    The method verbose returns a verbose message containing builder infos.
    """
    message = ''
    if not self.quiet:
      message = "Builder options"+"\n"
      message+= "  Compiled-objects .o   directory: "+builder.obj_dir+"\n"
      message+= "  Compiled-objects .mod directory: "+builder.mod_dir+"\n"
      message+= "  Building directory:              "+builder.build_dir+"\n"
      message+= "  Included paths:                  "+"".join([s+" " for s in builder.dinc])+"\n"
      message+= "  Linked libraries:                "+"".join([s+" " for s in builder.libs])+"\n"
      message+= "  Compiler class:                  "+builder.compiler+"\n"
      message+= "  Compiler:                        "+builder.fc+"\n"
      message+= "  Compiler module switch:          "+builder.modsw+"\n"
      message+= "  Compilation flags:               "+builder.cflags+"\n"
      message+= "  Linking     flags:               "+builder.lflags+"\n"
      message+= "  Preprocessing flags:             "+builder.preproc+"\n"
    return message
class Cleaner(object):
  """
  Cleaner is an object for cleaning current project.
  """
  def __init__(self,
               build_dir = "./",    # directory containing built files
               mod_dir   = "./",    # directory containing .mod files
               obj_dir   = "./",    # directory containing compiled object files
               target    = None,    # target files
               output    = None,    # names of compiled tragets
               mklib     = None,    # create library
               colors    = False):  # make printings colored
    self.build_dir = build_dir
    self.mod_dir   = build_dir+mod_dir
    self.obj_dir   = build_dir+obj_dir
    self.target    = target
    self.output    = output
    self.mklib     = mklib
    self.colors    = Colors()
    if not colors:
      self.colors.disable()
  def clean_mod(self):
    """
    Function clean_mod clean compiled MODs directory.
    """
    if os.path.exists(self.mod_dir):
      print self.colors.red+'Removing '+self.mod_dir+self.colors.end
      shutil.rmtree(self.mod_dir)
  def clean_obj(self):
    """
    Function clean_obj clean compiled OBJs directory.
    """
    if os.path.exists(self.obj_dir):
      print self.colors.red+'Removing '+self.obj_dir+self.colors.end
      shutil.rmtree(self.obj_dir)
  def clean_target(self):
    """
    Function clean_target clean compiled targets.
    """
    if self.target:
      if self.output:
        exe = self.output
      else:
        if self.mklib:
          if self.mklib.lower()=='static':
            exe = os.path.splitext(os.path.basename(self.target))[0]+'.a'
          elif self.mklib.lower()=='shared':
            exe = os.path.splitext(os.path.basename(self.target))[0]+'.so'
        else:
          exe = os.path.splitext(os.path.basename(self.target))[0]
      if os.path.exists(self.build_dir+exe):
        print self.colors.red+'Removing '+self.build_dir+exe+self.colors.end
        os.remove(self.build_dir+exe)
      if os.path.exists('build_'+os.path.splitext(os.path.basename(self.target))[0]+'.log'):
        print self.colors.red+'Removing build_'+os.path.splitext(os.path.basename(self.target))[0]+'.log'+self.colors.end
        os.remove('build_'+os.path.splitext(os.path.basename(self.target))[0]+'.log')
class Dependency(object):
  """
  Dependency is an object that handles a single file dependency, its attributes and methods.
  """
  def __init__(self,
               type = "",  # type of dependency: "module" or "include" type
               name = "",  # name of dependency: module name for "use" type or file name for include type
               file = ""): # file name containing module in the case of "use" type
    self.type = type
    self.name = name
    self.file = file
class Parsed_file(object):
  """
  Parsed_file is an object that handles a single parsed file, its attributes and methods.
  """
  def __init__(self,
               name,                     # file name
               program      = False,     # flag for checking if the file is a program
               module       = False,     # flag for checking if the file is a modules file
               include      = False,     # flag for checking if the file is an include-dependency
               nomodlib     = False,     # flag for checking if the file is library of procedures with an enclosing module (old Fortran style)
               to_compile   = False,     # flag for checking if the file must be compiled
               output       = None):     # eventual user-supplied output file name
    self.name         = name
    self.program      = program
    self.module       = module
    self.include      = include
    self.nomodlib     = nomodlib
    self.to_compile   = to_compile
    self.output       = output
    self.basename     = os.path.splitext(os.path.basename(self.name))[0]
    self.timestamp    = os.path.getmtime(self.name)
    self.order        = 0
  def parse(self):
    """
    The method parse parses the file creating its the dependencies list and the list of modules names that self eventually contains.
    """
    self.module_names = []
    self.dependencies = []
    ffile = open(self.name, "r")
    for line in ffile:
      matching = re.match(regex_f95_program,line)
      if matching:
        self.program = True
      matching = re.match(regex_f95_module,line)
      if matching:
        self.module = True
        self.module_names.append(matching.group('name'))
      matching = re.match(regex_f95_use_mod,line)
      if matching:
        if not re.match(regex_f95_intrinsic,line):
          if matching.group('name').lower()!='mpi' and matching.group('name').lower()!='omp_lib':
            dep = Dependency(type="module",name=matching.group('name'))
            self.dependencies.append(dep)
      matching = re.match(regex_f95_include,line)
      if matching:
        if not re.match(regex_f95_mpifh,line):
          dep = Dependency(type="include",name=matching.group('name'))
          self.dependencies.append(dep)
    ffile.close()
    if not self.program and not self.module:
      if os.path.splitext(os.path.basename(self.name))[1] not in __extensions_inc__:
        self.nomodlib = True
  def save_build_log(self,builder):
    """
    The method save_build_log save a log file containing information about the building options used.
    """
    log_file = open("build_"+self.basename+".log", "w")
    log_file.writelines("Hierarchical dependencies list of: "+self.name+"\n")
    for dep in self.pfile_dep:
      log_file.writelines("  "+dep.name+"\n")
      log_file.writelines(dep.str_dependencies(pref="    "))
    log_file.writelines("Complete ordered dependencies list of: "+self.name+"\n")
    for dep in self.pfile_dep_all:
      log_file.writelines("  "+dep.name+"\n")
    log_file.writelines(builder.verbose())
    log_file.close()
  def str_dependencies(self,
                       pref = ""): # prefixing string
    """
    The method str_dependencies create a string containing the depencies files list.
    """
    str_dep = ""
    for dep in self.pfile_dep:
      str_dep = str_dep+pref+dep.name+"\n"
    return str_dep
  def obj_dependencies(self):
    """
    The method obj_dependencies create a list containing the dependencies object files list.
    """
    return [p.basename+".o" for p in self.pfile_dep_all if not p.include]
  def check_compile(self,obj_dir):
    """
    The method check_compile checks if self must be compiled.
    """
    if not self.include:
      # verifying if dependencies are up-to-date
      for dep in self.pfile_dep_all:
        if not dep.include:
          obj = obj_dir+dep.basename+".o"
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
            print " Attention: file "+dep.name+" does not exist, but it is a dependency of file "+self.name
            sys.exit(1)
          else:
            # comparing the include dependency with the self-compiled-object if exist
            obj = obj_dir+self.basename+".o"
            # verifying if dep is up-to-date
            if os.path.exists(obj):
              if os.path.getmtime(obj) < os.path.getmtime(dep.name):
                # found an include that is newer than self-compiled-object, thus self must be compiled
                self.to_compile = True
      # verifying if self is up-to-date
      if not self.to_compile:
        obj = obj_dir+self.basename+".o"
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
# auxiliary functions definitions
def traverse_recursive(pfile, path=list()):
  """
  The function traverse_recursive performs a yeld-recursive traversing of pfile direct dependencies.
  """
  path.append(pfile)
  yield path
  for n in pfile.pfile_dep:
    if n != pfile:
      for path in traverse_recursive(n, path):
          yield path
  if path:
      path.pop()
def unique_seq(seq):
  """
  The function unique_seq returns the input sequence removing duplicated elements but peserving the original order.
  """
  seen = set()
  seen_add = seen.add
  return [ x for x in seq if x not in seen and not seen_add(x)]
def module_is_in(pfiles,module):
  """
  The function module_is_in finds the parsed file containing the desidered module.
  """
  filename = ""
  n = -1
  for f,pfile in enumerate(pfiles):
    if pfile.module:
      for module_name in pfile.module_names:
        if module_name.lower()==module.lower():
          filename = pfile.name
          n = f
          break
  return filename,n
def include_is_in(pfiles,include):
  """
  The function include_is_in find the parsed file containing the desidered include-file.
  """
  filename = ""
  n = -1
  for f,pfile in enumerate(pfiles):
    if os.path.basename(pfile.name)==include:
      filename = pfile.name
      n = f
      break
  return filename,n
def dependency_hiearchy(builder,pfiles):
  """
  The function dependency_hiearchy builds parsed files hierarchy.
  """
  # direct dependencies list used after for building indirect (complete) dependencies list
  for pfile in pfiles:
    pfile.pfile_dep = []
    for dep in pfile.dependencies:
      if dep.type=="module":
        dep.file,n = module_is_in(pfiles=pfiles,module=dep.name)
        if n>-1:
          if not pfiles[n] in pfile.pfile_dep:
            pfile.pfile_dep.append(pfiles[n])
        else:
          print builder.colors.red+"Attention: the file '"+pfile.name+"' depends on '"+dep.name+"' that is unreachable"+builder.colors.end
          sys.exit(1)
      if dep.type=="include":
        dep.file,n = include_is_in(pfiles=pfiles,include=dep.name)
        if n>-1:
          if not pfiles[n] in pfile.pfile_dep:
            pfiles[n].program  = False
            pfiles[n].module   = False
            pfiles[n].nomodlib = False
            pfiles[n].include  = True
            pfile.pfile_dep.append(pfiles[n])
            if not os.path.dirname(pfiles[n].name) in builder.dinc:
              builder.dinc.append(os.path.dirname(pfiles[n].name))
        else:
          print builder.colors.red+"Attention: the file '"+pfile.name+"' depends on '"+dep.name+"' that is unreachable"+builder.colors.end
          sys.exit(1)
  # indirect dependency list
  for pfile in pfiles:
    pfile.create_pfile_dep_all()
  # using the just created hiearchy for checking which files must be (re-)compiled
  for pfile in pfiles:
    pfile.check_compile(obj_dir=builder.obj_dir)
def remove_other_main(builder,pfiles,me):
  """
  The function remove_other_main removes all compiled objects of other program than the current target under building.
  """
  for pfile in pfiles:
    if pfile.program and pfile.name!=me.name:
      if os.path.exists(builder.obj_dir+pfile.basename+".o"):
        os.remove(builder.obj_dir+pfile.basename+".o")
def inquire_fobos(cliargs,filename='fobos'):
  """
  The function inquire_fobos checks if a 'fobos' file is present in current working directory and, in case, parses it for CLI arguments overloading.
  """
  fobos_colors = Colors()
  cliargs_dict = deepcopy(cliargs.__dict__)
  if os.path.exists(filename):
    fobos = ConfigParser.ConfigParser()
    fobos.read(filename)
    if cliargs.which=='rule':
      if cliargs.list:
        print fobos_colors.bld+'The fobos file defines the following rules:'+fobos_colors.end
        for rule in fobos.sections():
          if rule.startswith('rule-'):
            if fobos.has_option(rule,'rule'):
              r = rule.split('rule-')
              print fobos_colors.bld+'  - "'+r[1]+'": '+fobos.get(rule,'rule')+fobos_colors.end
        sys.exit(0)
      elif cliargs.execute:
        rule = 'rule-'+cliargs.execute
        if fobos.has_option(rule,'rule'):
          print fobos_colors.bld+' Executing rule "'+cliargs.execute+'"'+fobos_colors.end
          syswork(fobos.get(rule,'rule'))
          sys.exit(0)
        else:
          print fobos_colors.red+'Error: the rule "'+cliargs.execute+'" is not defined into the fobos file. Defined rules are:'+fobos_colors.end
          for rule in fobos.sections():
            if rule.startswith('rule-'):
              if fobos.has_option(rule,'rule'):
                r = rule.split('rule-')
                print fobos_colors.red+'  - "'+r[1]+'": '+fobos.get(rule,'rule')+fobos_colors.end
          sys.exit(1)
    if cliargs.lmodes:
      if fobos.has_option('modes','modes'):
        print fobos_colors.bld+'The fobos file defines the following modes:'+fobos_colors.end
        for m in fobos.get('modes','modes').split():
          print fobos_colors.bld+'  - "'+m+'"'+fobos_colors.end
        sys.exit(0)
      else:
        print fobos_colors.red+'Error: no modes are defined into the fobos file!'+fobos_colors.end
        sys.exit(1)
    section = False
    if fobos.has_option('modes','modes'):
      if cliargs.mode:
        if cliargs.mode in fobos.get('modes','modes'):
          section = cliargs.mode
        else:
          print fobos_colors.red+'Error: the mode "'+cliargs.mode+'" is not defined into the fobos file. Defined modes are:'+fobos_colors.end
          for m in fobos.get('modes','modes').split():
            print fobos_colors.red+'  - "'+m+'"'+fobos_colors.end
          sys.exit(1)
      else:
        section = fobos.get('modes','modes').split()[0] # first mode selected
    if not section:
      if fobos.has_section('default'):
        section = 'default'
      else:
        print fobos_colors.red+'Error: fobos file has not "modes" section neither "default" one'+fobos_colors.end
        sys.exit(1)
    for item in fobos.items(section):
      if item[0] in cliargs_dict:
        if type(cliargs_dict[item[0]])==type(False):
          setattr(cliargs,item[0],fobos.getboolean(section,item[0]))
        elif type(cliargs_dict[item[0]])==type(1):
          setattr(cliargs,item[0],int(item[1]))
        elif type(cliargs_dict[item[0]])==type([]):
          setattr(cliargs,item[0],item[1].split())
        else:
          setattr(cliargs,item[0],item[1])
    for item in cliargs_dict:
      if item in ['cflags','lflags','preproc']:
        val_fobos = cliargs_dict[item]
        val_cli   = getattr(cliargs,item)
        if val_fobos and val_cli:
          setattr(cliargs,item,val_fobos+val_cli)
# main loop
if __name__ == '__main__':
  cliargs = cliparser.parse_args()
  if cliargs.fobos:
    inquire_fobos(cliargs=cliargs,filename=cliargs.fobos)
  else:
    inquire_fobos(cliargs=cliargs)
  if cliargs.which=='clean':
    cleaner=Cleaner(build_dir=cliargs.build_dir,obj_dir=cliargs.obj_dir,mod_dir=cliargs.mod_dir,target=cliargs.target,output=cliargs.output,mklib=cliargs.mklib,colors=cliargs.colors)
    # clean project
    if not cliargs.only_obj and not cliargs.only_target:
      cleaner.clean_mod()
      cleaner.clean_obj()
      cleaner.clean_target()
    if cliargs.only_obj:
      cleaner.clean_mod()
      cleaner.clean_obj()
    if cliargs.only_target:
      cleaner.clean_target()
  elif cliargs.which=='build':
    __extensions_inc__  += cliargs.inc
    builder=Builder(compiler=cliargs.compiler,fc=cliargs.fc,modsw=cliargs.modsw,mpi=cliargs.mpi,cflags=cliargs.cflags,lflags=cliargs.lflags,libs=cliargs.libs,dinc=cliargs.include,preproc=cliargs.preproc,build_dir=cliargs.build_dir,obj_dir=cliargs.obj_dir,mod_dir=cliargs.mod_dir,quiet=cliargs.quiet,colors=cliargs.colors,jobs=cliargs.jobs)
    pfiles = [] # main parsed files list
    # parsing files loop
    for root, subFolders, files in os.walk(cliargs.src):
      for filename in files:
        if any(os.path.splitext(os.path.basename(filename))[1]==ext for ext in __extensions_parsed__):
          if os.path.basename(filename) not in [os.path.basename(exc) for exc in cliargs.exclude]:
            file = os.path.join(root, filename)
            pfile = Parsed_file(name=file)
            pfile.parse()
            pfiles.append(pfile)
    # building dependencies hierarchy
    dependency_hiearchy(builder=builder,pfiles=pfiles)
    # compiling independent files that are libraries of procedures not contained into a module (old Fortran style)
    nomodlibs = []
    for pfile in pfiles:
      if pfile.nomodlib:
        builder.build(pfile=pfile)
        nomodlibs.append(pfile.basename+".o")
    # building target or all programs found
    for pfile in pfiles:
      if cliargs.target:
        if os.path.basename(cliargs.target)==os.path.basename(pfile.name):
          print builder.colors.bld+builder.verbose()+builder.colors.end
          if pfile.program:
            remove_other_main(builder=builder,pfiles=pfiles,me=pfile)
          builder.build(pfile=pfile,output=cliargs.output,nomodlibs=nomodlibs,mklib=cliargs.mklib)
          if cliargs.log:
            pfile.save_build_log(builder=builder)
      else:
        if pfile.program:
          print builder.colors.bld+builder.verbose()+builder.colors.end
          remove_other_main(builder=builder,pfiles=pfiles,me=pfile)
          builder.build(pfile=pfile,output=cliargs.output,nomodlibs=nomodlibs)
          if cliargs.log:
            pfile.save_build_log(builder=builder)
