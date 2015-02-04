#!/usr/bin/env python
"""
FoBiS.py, Fortran Building System for poor men
"""
__appname__ = 'FoBiS.py'
__version__ ="1.1.4"
__author__  = 'Stefano Zaghi'
# modules loading
import sys
import os
import time
import argparse
from copy import deepcopy
import subprocess
import shutil
try:
  import ConfigParser as configparser
except ImportError:
  import configparser
import operator
import re
try:
  from multiprocessing import Pool
  __parallel__=True
except ImportError:
  print("Module 'multiprocessing' not found: parallel compilation disabled")
  __parallel__=False
# setting CLI
__cliparser__ = argparse.ArgumentParser(prog=__appname__,description='FoBiS.py, Fortran Building System for poor men')
__cliparser__.add_argument('-v','--version',action='version',help='Show version',version='%(prog)s '+__version__)
__clisubparsers__ = __cliparser__.add_subparsers(title='Commands',description='Valid commands')
__buildparser__ = __clisubparsers__.add_parser('build',help='Build all programs found or a specific target')
__buildparser__.set_defaults(which='build')
__cleanparser__ = __clisubparsers__.add_parser('clean',help='Clean project: completely remove OBJ and MOD directories... use carefully')
__cleanparser__.set_defaults(which='clean')
__rulexparser__ = __clisubparsers__.add_parser('rule', help='Execute rules defined into a fobos file')
__rulexparser__.set_defaults(which='rule')
__buildparser__.add_argument('-f',       '--fobos',    required=False,action='store',               default=None,            help='Specify a "fobos" file named differently from "fobos"')
__buildparser__.add_argument('-colors',                required=False,action='store_true',          default=False,           help='Activate colors in shell prints [default: no colors]')
__buildparser__.add_argument('-l',       '--log',      required=False,action='store_true',          default=False,           help='Activate the creation of a log file [default: no log file]')
__buildparser__.add_argument('-q',       '--quiet',    required=False,action='store_true',          default=False,           help='Less verbose than default')
__buildparser__.add_argument('-j',       '--jobs',     required=False,action='store',               default=1,      type=int,help='Specify the number of concurrent jobs used for compiling dependencies [default 1]')
__buildparser__.add_argument('-compiler',              required=False,action='store',               default='Intel',         help='Compiler used: Intel, GNU, IBM, PGI, g95 or Custom [default: Intel]')
__buildparser__.add_argument('-fc',                    required=False,action='store',               default='',              help='Specify the Fortran compiler statement, necessary for custom compiler specification (-compiler Custom)')
__buildparser__.add_argument('-modsw',                 required=False,action='store',               default='',              help='Specify the switch for setting the module searching path, necessary for custom compiler specification (-compiler Custom)')
__buildparser__.add_argument('-mpi',                   required=False,action='store_true',          default=False,           help='Use MPI enabled version of compiler')
__buildparser__.add_argument('-cflags',                required=False,action='store',               default='-c',            help='Compile flags')
__buildparser__.add_argument('-lflags',                required=False,action='store',               default='',              help='Link flags')
__buildparser__.add_argument('-libs',                  required=False,action='store',     nargs='+',default=[],              help='List of external libraries used')
__buildparser__.add_argument('-i',       '--include',  required=False,action='store',     nargs='+',default=[],              help='List of directories for searching included files')
__buildparser__.add_argument('-inc',                   required=False,action='store',     nargs='+',default=[],              help='List of custom-defined file extensions for include files')
__buildparser__.add_argument('-p',       '--preproc',  required=False,action='store',               default='',              help='Preprocessor flags')
__buildparser__.add_argument('-dobj',    '--obj_dir',  required=False,action='store',               default='./obj/',        help='Directory containing compiled objects [default: ./obj/]')
__buildparser__.add_argument('-dmod',    '--mod_dir',  required=False,action='store',               default='./mod/',        help='Directory containing .mod files of compiled objects [default: ./mod/]')
__buildparser__.add_argument('-dbld',    '--build_dir',required=False,action='store',               default='./',            help='Directory containing executable objects [default: ./]')
__buildparser__.add_argument('-s',       '--src',      required=False,action='store',               default='./',            help='Root-directory of source files [default: ./]')
__buildparser__.add_argument('-e',       '--exclude',  required=False,action='store',     nargs='+',default=[],              help='Exclude a list of files from the building process')
__buildparser__.add_argument('-t',       '--target',   required=False,action='store',               default=None,            help='Specify a target file [default: all programs found]')
__buildparser__.add_argument('-o',       '--output',   required=False,action='store',               default=None,            help='Specify the output file name is used with -target switch [default: basename of target]')
__buildparser__.add_argument('-mklib',                 required=False,action='store',               default=None,            help='Build library instead of program (use with -target switch); usage: -mklib static or -mklib shared')
__buildparser__.add_argument('-mode',                  required=False,action='store',               default=None,            help='Select a mode defined into a fobos file')
__buildparser__.add_argument('-lmodes',                required=False,action='store_true',          default=False,           help='List the modes defined into a fobos file')
__buildparser__.add_argument('-m',       '--makefile', required=False,action='store',               default=None,            help='Generate a GNU Makefile for building the project', metavar='MAKEFILE_name')
__buildparser__.add_argument('-pfm',     '--preform',  required=False,action='store_true',          default=False,           help='Use PreForM.py pre-processor for pre-processing sources file')
__buildparser__.add_argument('-dpfm',    '--pfm_dir',  required=False,action='store',               default=None,            help='Directory containing the sources processed with PreForM.py [default: none, the processed files are removed after used]')
__buildparser__.add_argument('-epfm',    '--pfm_ext',  required=False,action='store',     nargs='+',default=[],              help='List of custom-defined file extensions to be preprocessed by PreForM.py [default: none, all files are preprocessed if PreForM.py is used]')
__cleanparser__.add_argument('-f',       '--fobos',    required=False,action='store',               default=None,            help='Specify a "fobos" file named differently from "fobos"')
__cleanparser__.add_argument('-colors',                required=False,action='store_true',          default=False,           help='Activate colors in shell prints [default: no colors]')
__cleanparser__.add_argument('-dobj',    '--obj_dir',  required=False,action='store',               default='./obj/',        help='Directory containing compiled objects [default: ./obj/]')
__cleanparser__.add_argument('-dmod',    '--mod_dir',  required=False,action='store',               default='./mod/',        help='Directory containing .mod files of compiled objects [default: ./mod/]')
__cleanparser__.add_argument('-dbld',    '--build_dir',required=False,action='store',               default='./',            help='Directory containing executable objects [default: ./]')
__cleanparser__.add_argument('-t',       '--target',   required=False,action='store',               default=None,            help='Specify a target file [default: all programs found]')
__cleanparser__.add_argument('-o',       '--output',   required=False,action='store',               default=None,            help='Specify the output file name is used with -target switch [default: basename of target]')
__cleanparser__.add_argument('-only_obj',              required=False,action='store_true',          default=False,           help='Clean only compiled objects and not also built targets')
__cleanparser__.add_argument('-only_target',           required=False,action='store_true',          default=False,           help='Clean only built targets and not also compiled objects')
__cleanparser__.add_argument('-mklib',                 required=False,action='store',               default=None,            help='Build library instead of program (use with -target switch); usage: -mklib static or -mklib shared')
__cleanparser__.add_argument('-mode',                  required=False,action='store',               default=None,            help='Select a mode defined into a fobos file')
__cleanparser__.add_argument('-lmodes',                required=False,action='store_true',          default=False,           help='List the modes defined into a fobos file')
__rulexparser__.add_argument('-f',       '--fobos',    required=False,action='store',               default=None,            help='Specify a "fobos" file named differently from "fobos"')
__rulexparser__.add_argument('-ex',      '--execute',  required=False,action='store',               default=None,            help='Specify a rule (defined into fobos file) to be executed', metavar='RULE')
__rulexparser__.add_argument('-ls',      '--list',     required=False,action='store_true',          default=False,           help='List the rules defined into a fobos file')
__rulexparser__.add_argument('-q',       '--quiet',    required=False,action='store_true',          default=False,           help='Less verbose than default')
# definition of regular expressions
__str_f95_apex__         = r"('|"+r'")'
__str_f95_kw_include__   = r"[Ii][Nn][Cc][Ll][Uu][Dd][Ee]"
__str_f95_kw_intrinsic__ = r"[Ii][Nn][Tt][Rr][Ii][Nn][Ss][Ii][Cc]"
__str_f95_kw_module__    = r"[Mm][Oo][Dd][Uu][Ll][Ee]"
__str_f95_kw_program__   = r"[Pp][Rr][Oo][Gg][Rr][Aa][Mm]"
__str_f95_kw_use__       = r"[Uu][Ss][Ee]"
__str_f95_kw_mpifh__     = r"[Mm][Pp][Ii][Ff]\.[Hh]"
__str_f95_name__         = r"(?P<name>[a-zA-Z][a-zA-Z0-9_]*)"
__str_f95_eol__          = r"(?P<eol>\s*!.*|\s*)?$"
__str_f95_mod_rename__   = r"(\s*,\s*[a-zA-Z][a-zA-Z0-9_]*\s*=>\s*[a-zA-Z][a-zA-Z0-9_]*)*"
__str_f95_mod_only__     = r"(\s*,\s*[Oo][Nn][Ll][Yy]\s*:\s*([a-zA-Z][a-zA-Z0-9_]*\s*=>\s*[a-zA-Z][a-zA-Z0-9_]*|[a-zA-Z][a-zA-Z0-9_]*))*"
__str_f95_use_mod__      = (r"^(\s*)"              + # eventual initial white spaces
                            __str_f95_kw_use__     + # f95 keyword "use"
                            r"(\s+)"               + # 1 or more white spaces
                            __str_f95_name__       + # f95 construct name
                            r"(?P<mod_eol>(.*))")
__str_f95_include__      = (r"^(\s*|\#)"           + # eventual initial white spaces or "#" character
                            __str_f95_kw_include__ + # f95 keyword "include"
                            r"(\s+)"               + # 1 or more white spaces
                            __str_f95_apex__       + # character "'" or '"'
                            r"(\s*)"               + # eventaul white spaces
                            r"(?P<name>.*)"        + # name of included file
                            r"(\s*)"               + # eventaul white spaces
                            __str_f95_apex__       + # character "'" or '"'
                            __str_f95_eol__)         # eventual eol white space and or comment
__str_f95_module__       = (r"^(\s*)"                                   + # eventual initial white spaces
                            r"(?P<scplevel>"+__str_f95_kw_module__+r")" + # f95 keyword "module"
                            r"(\s+)"                                    + # 1 or more white spaces
                            __str_f95_name__                            + # f95 construct name
                            __str_f95_eol__)                              # eventual eol white space and or comment
__str_f95_program__      = (r"^(\s*)"                                    + # eventual initial white spaces
                            r"(?P<scplevel>"+__str_f95_kw_program__+r")" + # f95 keyword "program"
                            r"(\s+)"                                     + # 1 or more white spaces
                            __str_f95_name__                             + # f95 construct name
                            __str_f95_eol__)                               # eventual eol white space and or comment
__str_f95_intrinsic__    = (r"(,\s*)"+__str_f95_kw_intrinsic__+r"(\s+)")
__str_f95_mpifh__        = (r"(.*)"+__str_f95_kw_mpifh__+r"(.*)")
__regex_f95_use_mod__    = re.compile(__str_f95_use_mod__)
__regex_f95_include__    = re.compile(__str_f95_include__)
__regex_f95_program__    = re.compile(__str_f95_program__)
__regex_f95_module__     = re.compile(__str_f95_module__)
__regex_f95_intrinsic__  = re.compile(__str_f95_intrinsic__)
__regex_f95_mpifh__      = re.compile(__str_f95_mpifh__)
__extensions_old__    = [".f",".F",".for",".FOR",".fpp",".FPP",".fortran",".f77",".F77"]
__extensions_modern__ = [".f90",".F90",".f95",".F95",".f03",".F03",".f08",".F08",".f2k",".F2K"]
__extensions_inc__    = [".inc",".INC",".h",".H"]
__extensions_parsed__ = __extensions_old__ + __extensions_modern__
# system worker function
def syswork(cmd):
  """
  Function for executing system command 'cmd': for compiling and linking files.
  """
  error = 0
  try:
    output = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT)
    # if output:
    #   print(output)
  except subprocess.CalledProcessError as err:
    error = err.returncode
    output = err.output
  return [error,output]

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
  """Builder is an object that handles the building system, its attributes and methods."""
  def __init__(self, compiler = "Intel", fc = "", modsw = "", mpi = False, cflags = "", lflags = "", libs = None, dinc = None, preproc = "", build_dir = "./", mod_dir = "./", obj_dir = "./", quiet = False, colors = False, jobs = 1, preform = False, pfm_dir = None, pfm_ext = []):
    """
    Parameters
    ----------
    compiler : {"Intel"}
      compiler used
    fc : {""}
      custom compiler statement
    modsw : {""}
      custom compiler switch for modules searching path
    mpi : {False}
      use MPI enabled version of compiler
    cflags : {""}
      compilation flags
    lflags : {""}
      linking flags
    libs : {None}
      list of external libraries
    dinc : {None}
      list of directories for searching included files
    preproc : {""}
      preprocessor flags
    build_dir : {"./"}
      directory containing built files
    mod_dir : {"./"}
      directory containing .mod files
    obj_dir : {"./"}
      directory containing compiled object files
    quiet : {False}
      make printings less verbose than default
    colors : {False}
      make printings colored
    jobs : {1}
      concurrent compiling jobs
    preform : {False}
      activate PreForM.py pre-processing
    pfm_dir : {None}
      directory containing sources processed by PreForm.py; by default are removed after used
    pfm_ext : {[]}
      list of file extensions to be processed by PreForm.py; by default all files are preprocessed if PreForM.py is used

    Attributes
    ----------
    """
    self.compiler  = compiler
    self.fcs       = fc
    self.modsw     = modsw
    self.mpi       = mpi
    self.cflags    = cflags
    self.lflags    = lflags
    if libs is None:
      self.libs = []
    else:
      self.libs = libs
    if dinc is None:
      self.dinc = []
    else:
      self.dinc = dinc
    self.preproc   = preproc
    self.build_dir = build_dir
    self.mod_dir   = build_dir+mod_dir
    self.obj_dir   = build_dir+obj_dir
    self.quiet     = quiet
    self.colors    = Colors()
    self.jobs      = jobs
    self.preform   = preform
    self.pfm_ext   = pfm_ext
    self.pfm_dir   = pfm_dir
    if self.pfm_dir: self.pfm_dir = build_dir+self.pfm_dir
    if not colors:
      self.colors.disable()
    if self.preform:
      pfm_exist = False
      for path in os.environ["PATH"].split(os.pathsep):
        pfm_exist = os.path.exists(os.path.join(path, 'PreForM.py'))
        if pfm_exist:
          if self.pfm_dir:
            if not os.path.exists(self.pfm_dir):
              os.makedirs(self.pfm_dir)
          break
      if not pfm_exist:
        print(self.colors.red+'Error: PreForM.py is not in your PATH! You cannot use --preform or -pfm switches.'+self.colors.end)
        sys.exit(1)
    if mpi:
      self.fcs = 'mpif90'
    if compiler.lower() == 'gnu':
      if not mpi:
        self.fcs = 'gfortran'
      self.modsw = '-J'
    elif compiler.lower() == 'intel':
      if not mpi:
        self.fcs = 'ifort'
      self.modsw = '-module'
    elif compiler.lower() == 'g95':
      if not mpi:
        self.fcs = 'g95'
      self.modsw = '-fmod='
    elif compiler.lower() == 'custom':
      pass # all is set from CLI
    if self.modsw[-1]!='=': # check necessary for g95 CLI trapping error
      self.modsw += ' '
    self.cmd_comp = self.fcs+' '+self.cflags+' '+self.modsw+self.mod_dir+' '+self.preproc
    self.cmd_link = self.fcs+' '+self.lflags+' '+self.modsw+self.mod_dir
    # checking paths integrity
    if not os.path.exists(self.mod_dir):
      os.makedirs(self.mod_dir)
    if not os.path.exists(self.obj_dir):
      os.makedirs(self.obj_dir)
    if not os.path.exists(self.build_dir):
      os.makedirs(self.build_dir)

  def compile_command(self,file_to_compile):
    """
    The method compile_command returns the OS command for compiling file_to_compile.

    Parameters
    ----------
    file_to_compile : ParsedFile object
      file to be compiled

    Returns
    -------
    str
      string containing the compile command
    """
    if self.preform:
      if len(self.pfm_ext)>0:
        if file_to_compile.extension in self.pfm_ext:
          if self.pfm_dir:
            if len(self.dinc)>0:
              comp_cmd = 'PreForM.py '+file_to_compile.name+' -o '+self.pfm_dir+file_to_compile.basename+'.pfm.f90'+' ; '+self.cmd_comp+' '+''.join(['-I'+s+' ' for s in self.dinc])+self.pfm_dir+file_to_compile.basename+'.pfm.f90'+' -o '+self.obj_dir+file_to_compile.basename+'.o'
            else:
              comp_cmd = 'PreForM.py '+file_to_compile.name+' -o '+self.pfm_dir+file_to_compile.basename+'.pfm.f90'+' ; '+self.cmd_comp+' '+                                         self.pfm_dir+file_to_compile.basename+'.pfm.f90'+' -o '+self.obj_dir+file_to_compile.basename+'.o'
          else:
            if len(self.dinc)>0:
              comp_cmd = 'PreForM.py '+file_to_compile.name+' -o '+file_to_compile.basename+'.pfm.f90'+' ; '+self.cmd_comp+' '+''.join(['-I'+s+' ' for s in self.dinc])+file_to_compile.basename+'.pfm.f90'+' -o '+self.obj_dir+file_to_compile.basename+'.o'+' ; rm -f '+file_to_compile.basename+'.pfm.f90'
            else:
              comp_cmd = 'PreForM.py '+file_to_compile.name+' -o '+file_to_compile.basename+'.pfm.f90'+' ; '+self.cmd_comp+' '+                                         file_to_compile.basename+'.pfm.f90'+' -o '+self.obj_dir+file_to_compile.basename+'.o'+' ; rm -f '+file_to_compile.basename+'.pfm.f90'
        else:
          if len(self.dinc)>0:
            comp_cmd = self.cmd_comp+' '+''.join(['-I'+s+' ' for s in self.dinc])+file_to_compile.name+' -o '+self.obj_dir+file_to_compile.basename+'.o'
          else:
            comp_cmd = self.cmd_comp+' '                                         +file_to_compile.name+' -o '+self.obj_dir+file_to_compile.basename+'.o'
      else:
        if self.pfm_dir:
          if len(self.dinc)>0:
            comp_cmd = 'PreForM.py '+file_to_compile.name+' -o '+self.pfm_dir+file_to_compile.basename+'.pfm'+file_to_compile.extension+' ; '+self.cmd_comp+' '+''.join(['-I'+s+' ' for s in self.dinc])+self.pfm_dir+file_to_compile.basename+'.pfm'+file_to_compile.extension+' -o '+self.obj_dir+file_to_compile.basename+'.o'
          else:
            comp_cmd = 'PreForM.py '+file_to_compile.name+' -o '+self.pfm_dir+file_to_compile.basename+'.pfm'+file_to_compile.extension+' ; '+self.cmd_comp+' '+                                         self.pfm_dir+file_to_compile.basename+'.pfm'+file_to_compile.extension+' -o '+self.obj_dir+file_to_compile.basename+'.o'
        else:
          if len(self.dinc)>0:
            comp_cmd = 'PreForM.py '+file_to_compile.name+' -o '+file_to_compile.basename+'.pfm'+file_to_compile.extension+' ; '+self.cmd_comp+' '+''.join(['-I'+s+' ' for s in self.dinc])+file_to_compile.basename+'.pfm'+file_to_compile.extension+' -o '+self.obj_dir+file_to_compile.basename+'.o'+' ; rm -f '+file_to_compile.basename+'.pfm'+file_to_compile.extension
          else:
            comp_cmd = 'PreForM.py '+file_to_compile.name+' -o '+file_to_compile.basename+'.pfm'+file_to_compile.extension+' ; '+self.cmd_comp+' '+                                         file_to_compile.basename+'.pfm'+file_to_compile.extension+' -o '+self.obj_dir+file_to_compile.basename+'.o'+' ; rm -f '+file_to_compile.basename+'.pfm'+file_to_compile.extension
    else:
      if len(self.dinc)>0:
        comp_cmd = self.cmd_comp+' '+''.join(['-I'+s+' ' for s in self.dinc])+file_to_compile.name+' -o '+self.obj_dir+file_to_compile.basename+'.o'
      else:
        comp_cmd = self.cmd_comp+' '                                         +file_to_compile.name+' -o '+self.obj_dir+file_to_compile.basename+'.o'
    return comp_cmd

  def build(self,file_to_build,output=None,nomodlibs=None,mklib=None):
    """
    Method for building file.

    Parameters
    ----------
    file_to_build : ParsedFile
    output :
    nomodlibs : {None}
      list of old-Fortran style libraries objects
    mklib : {None}
    """
    print(self.colors.bld+'Building '+file_to_build.name+self.colors.end)
    # correct the list ordering accordingly to indirect dependency
    for dep in file_to_build.pfile_dep_all:
      for other_dep in file_to_build.pfile_dep_all:
        if other_dep != dep:
          if dep in other_dep.pfile_dep_all:
            dep.order+=1
    file_to_build.pfile_dep_all.sort(key=operator.attrgetter('order'),reverse=True)
    # creating a hierarchy list of compiling commands accordingly to the order of all dependencies
    if len([p for p in file_to_build.pfile_dep_all if not p.include and p.to_compile])>0:
      order_max = max([p for p in file_to_build.pfile_dep_all if not p.include and p.to_compile],key=operator.attrgetter('order')).order + 1
      hierarchy = [[] for i in range(order_max)]
      for dep in file_to_build.pfile_dep_all:
        if dep.to_compile and not dep.include:
          hierarchy[dep.order].append([dep.name,self.compile_command(file_to_compile=dep)])
          dep.to_compile = False
      hierarchy = [h for h in hierarchy if len(h)>0]
      for deps in reversed(hierarchy):
        files_to_compile = ''
        cmds = []
        for dep in deps:
          files_to_compile = files_to_compile+" "+dep[0]
          cmds.append(dep[1])
        if len(deps)>1 and self.jobs>1 and __parallel__:
          jobs = min(len(deps),self.jobs)
          print(self.colors.bld+"Compiling"+files_to_compile+" using "+str(jobs)+" concurrent processes"+self.colors.end)
          pool = Pool(processes=jobs)
          results = pool.map(syswork,cmds)
          pool.close()
          pool.join()
          if not all(v[0] == 0 for v in results):
            for result in results:
              if result[0] != 0:
                print(self.colors.red+result[1]+self.colors.end)
            sys.exit(1)
          if not all(v[1] == '' for v in results):
            for result in results:
              if result[1] != '':
                print(self.colors.red+result[1]+self.colors.end)
        else:
          print(self.colors.bld+"Compiling"+files_to_compile+" serially "+self.colors.end)
          for cmd in cmds:
            result = syswork(cmd)
            if result[0] != 0:
              print(self.colors.red+result[1]+self.colors.end)
              sys.exit(1)
    else:
      print(self.colors.bld+'Nothing to compile, all objects are up-to-date'+self.colors.end)
    if file_to_build.program:
      if nomodlibs is not None:
        objs = nomodlibs + file_to_build.obj_dependencies()
      else:
        objs =             file_to_build.obj_dependencies()
      if output:
        exe=self.build_dir+output
      else:
        exe=self.build_dir+file_to_build.basename
      link_cmd = self.cmd_link+" "+"".join([self.obj_dir+s+" " for s in objs])+"".join([s+" " for s in self.libs])+"-o "+exe
      print(self.colors.bld+"Linking "+exe+self.colors.end)
      result = syswork(link_cmd)
      if result[0] != 0:
        print(self.colors.red+result[1]+self.colors.end)
        sys.exit(1)
      print(self.colors.bld+'Target '+file_to_build.name+' has been successfully built'+self.colors.end)
    elif mklib:
      if output:
        lib=self.build_dir+output
      else:
        if mklib.lower()=='shared':
          lib=self.build_dir+file_to_build.basename+'.so'
        elif mklib.lower()=='static':
          lib=self.build_dir+file_to_build.basename+'.a'
      if mklib.lower()=='shared':
        link_cmd = self.cmd_link+" "+"".join([s+" " for s in self.libs])+self.obj_dir+file_to_build.basename+".o -o "+lib
      elif mklib.lower()=='static':
        link_cmd = "ar -rcs "+lib+" "+self.obj_dir+file_to_build.basename+".o ; ranlib "+lib
      print(self.colors.bld+"Linking "+lib+self.colors.end)
      result = syswork(link_cmd)
      if result[0] != 0:
        print(self.colors.red+result[1]+self.colors.end)
        sys.exit(1)
      print(self.colors.bld+'Target '+file_to_build.name+' has been successfully built'+self.colors.end)

  def verbose(self):
    """
    The method verbose returns a verbose message containing builder infos.
    """
    message = ''
    if not self.quiet:
      message = "Builder options"+"\n"
      message+= "  Compiled-objects .o   directory: "+__builder__.obj_dir+"\n"
      message+= "  Compiled-objects .mod directory: "+__builder__.mod_dir+"\n"
      message+= "  Building directory:              "+__builder__.build_dir+"\n"
      message+= "  Included paths:                  "+"".join([s+" " for s in __builder__.dinc])+"\n"
      message+= "  Linked libraries:                "+"".join([s+" " for s in __builder__.libs])+"\n"
      message+= "  Compiler class:                  "+__builder__.compiler+"\n"
      message+= "  Compiler:                        "+__builder__.fcs+"\n"
      message+= "  Compiler module switch:          "+__builder__.modsw+"\n"
      message+= "  Compilation flags:               "+__builder__.cflags+"\n"
      message+= "  Linking     flags:               "+__builder__.lflags+"\n"
      message+= "  Preprocessing flags:             "+__builder__.preproc+"\n"
      message+= "  PreForM.py used:                 "+str(__builder__.preform)+"\n"
      message+= "  PreForM.py output directory:     "+str(__builder__.pfm_dir)+"\n"
      message+= "  PreForM.py extensions processed: "+str(__builder__.pfm_ext)+"\n"
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
      print(self.colors.red+'Removing '+self.mod_dir+self.colors.end)
      shutil.rmtree(self.mod_dir)

  def clean_obj(self):
    """
    Function clean_obj clean compiled OBJs directory.
    """
    if os.path.exists(self.obj_dir):
      print(self.colors.red+'Removing '+self.obj_dir+self.colors.end)
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
        print(self.colors.red+'Removing '+self.build_dir+exe+self.colors.end)
        os.remove(self.build_dir+exe)
      if os.path.exists('build_'+os.path.splitext(os.path.basename(self.target))[0]+'.log'):
        print(self.colors.red+'Removing build_'+os.path.splitext(os.path.basename(self.target))[0]+'.log'+self.colors.end)
        os.remove('build_'+os.path.splitext(os.path.basename(self.target))[0]+'.log')

class Dependency(object):
  """
  Dependency is an object that handles a single file dependency, its attributes and methods.
  """
  def __init__(self, dtype = "", name = "", dfile = ""):
    """
    Parameters
    ----------
    dtype : {""}
      type of dependency: "module" or "include" type
    name : {""}
      name of dependency: module name for "use" type or file name for include type
    file : {""}
      file name containing module in the case of "use" type

    Attributes
    ----------
    """
    self.type = dtype
    self.name = name
    self.file = dfile

class ParsedFile(object):
  """ParsedFile is an object that handles a single parsed file, its attributes and methods."""
  def __init__(self, name, program = False, module = False, include = False, nomodlib = False, to_compile = False, output = None):
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
    self.name          = name
    self.program       = program
    self.module        = module
    self.include       = include
    self.nomodlib      = nomodlib
    self.to_compile    = to_compile
    self.output        = output
    self.basename      = os.path.splitext(os.path.basename(self.name))[0]
    self.extension     = os.path.splitext(os.path.basename(self.name))[1]
    self.timestamp     = os.path.getmtime(self.name)
    self.order         = 0
    self.pfile_dep     = None
    self.pfile_dep_all = None
    self.module_names  = None
    self.dependencies  = None

  def parse(self):
    """
    The method parse parses the file creating its the dependencies list and the list of modules names that self eventually contains.
    """
    self.module_names = []
    self.dependencies = []
    ffile = open(self.name, "r")
    for line in ffile:
      matching = re.match(__regex_f95_program__,line)
      if matching:
        self.program = True
      matching = re.match(__regex_f95_module__,line)
      if matching:
        self.module = True
        self.module_names.append(matching.group('name'))
      matching = re.match(__regex_f95_use_mod__,line)
      if matching:
        if not re.match(__regex_f95_intrinsic__,line):
          if matching.group('name').lower()!='mpi' and matching.group('name').lower()!='omp_lib':
            dep = Dependency(dtype="module",name=matching.group('name'))
            self.dependencies.append(dep)
      matching = re.match(__regex_f95_include__,line)
      if matching:
        if not re.match(__regex_f95_mpifh__,line):
          dep = Dependency(dtype="include",name=matching.group('name'))
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

  def save_makefile(self,makefile,builder):
    """
    The method save_makefile save a minimal makefile for building the file by means of GNU Make.
    """
    if not self.include:
      mk_file = open(makefile, "a")
      file_dep = [self.name]
      for dep in self.pfile_dep:
        if dep.include:
          file_dep.append(dep.name)
      if (len(self.pfile_dep)-len(file_dep))>=0:
        mk_file.writelines("$(DOBJ)"+self.basename.lower()+".o:"+"".join([" "+f for f in file_dep])+" \\"+"\n")
        for dep in self.pfile_dep[:-1]:
          if not dep.include:
            mk_file.writelines("\t$(DOBJ)"+os.path.splitext(os.path.basename(dep.name))[0].lower()+".o \\"+"\n")
        if not self.pfile_dep[-1].include:
          mk_file.writelines("\t$(DOBJ)"+os.path.splitext(os.path.basename(self.pfile_dep[-1].name))[0].lower()+".o\n")
      else:
        mk_file.writelines("$(DOBJ)"+self.basename.lower()+".o:"+"".join([" "+f for f in file_dep])+"\n")
      mk_file.writelines("\t@echo $(COTEXT)\n")
      mk_file.writelines("\t@$(FC) $(OPTSC) $(PREPROC) "+''.join(['-I'+i+' ' for i in builder.dinc])+" $< -o $@\n")
      mk_file.writelines("\n")
      mk_file.close()

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
            print(" Attention: file "+dep.name+" does not exist, but it is a dependency of file "+self.name)
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
def traverse_recursive(parsed_file, path=list()):
  """
  The function traverse_recursive performs a yield-recursive traversing of pfile direct dependencies.
  """
  path.append(parsed_file)
  yield path
  for dep in parsed_file.pfile_dep:
    if dep != parsed_file:
      for path in traverse_recursive(dep, path):
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
  Function finding the parsed file containing the desidered module.

  Parameters
  ----------
  pfiles : list
    list of parsed files
  module : str
    module name

  Returns
  -------
  file_name : str
    name of file containing the module
  number : int
    number of file containing the module
  """
  file_name = ""
  number = -1
  for fnum,parsed_file in enumerate(pfiles):
    if parsed_file.module:
      for module_name in parsed_file.module_names:
        if module_name.lower()==module.lower():
          file_name = parsed_file.name
          number = fnum
          break
  return file_name,number

def include_is_in(pfiles,include):
  """
  Function finding the parsed file containing the desidered include-file.

  Parameters
  ----------
  pfiles : list
    list of parsed files
  include : str
    include-file name

  Returns
  -------
  file_name : str
    name of file containing the include-file
  number : int
    number of file containing the include-file
  """
  file_name = ""
  number = -1
  for fnum,parsed_file in enumerate(pfiles):
    if os.path.basename(parsed_file.name)==include:
      file_name = parsed_file.name
      number = fnum
      break
  return file_name,number

def dependency_hiearchy(builder,pfiles):
  """
  The function dependency_hiearchy builds parsed files hierarchy.
  """
  # direct dependencies list used after for building indirect (complete) dependencies list
  for parsed_file in pfiles:
    parsed_file.pfile_dep = []
    for dep in parsed_file.dependencies:
      if dep.type=="module":
        dep.file,fnum = module_is_in(pfiles=pfiles,module=dep.name)
        if fnum>-1:
          if not pfiles[fnum] in parsed_file.pfile_dep:
            parsed_file.pfile_dep.append(pfiles[fnum])
        else:
          print(builder.colors.red+"Attention: the file '"+parsed_file.name+"' depends on '"+dep.name+"' that is unreachable"+builder.colors.end)
          sys.exit(1)
      if dep.type=="include":
        dep.file,fnum = include_is_in(pfiles=pfiles,include=dep.name)
        if fnum>-1:
          if not pfiles[fnum] in parsed_file.pfile_dep:
            pfiles[fnum].program  = False
            pfiles[fnum].module   = False
            pfiles[fnum].nomodlib = False
            pfiles[fnum].include  = True
            parsed_file.pfile_dep.append(pfiles[fnum])
            if not os.path.dirname(pfiles[fnum].name) in builder.dinc:
              builder.dinc.append(os.path.dirname(pfiles[fnum].name))
        else:
          print(builder.colors.red+"Attention: the file '"+parsed_file.name+"' depends on '"+dep.name+"' that is unreachable"+builder.colors.end)
          sys.exit(1)
  # indirect dependency list
  for parsed_file in pfiles:
    parsed_file.create_pfile_dep_all()
  # using the just created hiearchy for checking which files must be (re-)compiled
  for parsed_file in pfiles:
    parsed_file.check_compile(obj_dir=builder.obj_dir)

def remove_other_main(builder,pfiles,mysefl):
  """
  The function remove_other_main removes all compiled objects of other program than the current target under building.
  """
  for parsed_file in pfiles:
    if parsed_file.program and parsed_file.name!=mysefl.name:
      if os.path.exists(builder.obj_dir+parsed_file.basename+".o"):
        os.remove(builder.obj_dir+parsed_file.basename+".o")

def inquire_fobos(cliargs,fobosfile='fobos'):
  """
  The function inquire_fobos checks if a 'fobos' file is present in current working directory and, in case, parses it for CLI arguments overloading.
  """
  def modes_list(fobos=None,txtcolor='',colorend=''):
    """
    The function modes_list print the list of modes defined into fobos file.
    """
    if fobos.has_option('modes','modes'):
      modes = fobos.get('modes','modes').split()
      for mode in modes:
        if fobos.has_section(mode):
          if fobos.has_option(mode,'help'):
            helpmsg = fobos.get(mode,'help')
          else:
            helpmsg = ''
          print(txtcolor+'  - "'+mode+'" '+colorend+helpmsg)
    return

  def rules_list(cliargs=None,fobos=None,txtcolor='',colorend=''):
    """
    The function rules_list print the list of rules defined into fobos file.
    """
    for rule in fobos.sections():
      if rule.startswith('rule-'):
        if fobos.has_option(rule,'help'):
          helpmsg = fobos.get(rule,'help')
        else:
          helpmsg = ''
        print(txtcolor+'  - "'+rule.split('rule-')[1]+'" '+colorend+helpmsg)
        if fobos.has_option(rule,'quiet'):
          quiet = fobos.getboolean(rule,'quiet')
        else:
          quiet = cliargs.quiet
        for rul in fobos.options(rule):
          if rul.startswith('rule'):
            if not quiet:
              print(txtcolor+'       Command => '+fobos.get(rule,rul)+colorend)
    return

  fobos_colors = Colors()
  cliargs_dict = deepcopy(cliargs.__dict__)
  local_variables = {}
  if os.path.exists(fobosfile):
    fobos = configparser.ConfigParser()
    fobos.optionxform = str # case sensitive
    fobos.read(fobosfile)
    # checking if local variables have been defined into fobos
    for section in fobos.sections():
      for item in fobos.items(section):
        if item[0].startswith('$'):
          local_variables[item[0]] = item[1]
    # switch cases accordingly to cliargs
    if cliargs.which=='rule':
      if cliargs.list:
        print(fobos_colors.bld+'The fobos file defines the following rules:'+fobos_colors.end)
        rules_list(cliargs=cliargs,fobos=fobos,txtcolor=fobos_colors.bld,colorend=fobos_colors.end)
        sys.exit(0)
      elif cliargs.execute:
        rule = 'rule-'+cliargs.execute
        print(fobos_colors.bld+' Executing rule "'+cliargs.execute+'"'+fobos_colors.end)
        if fobos.has_section(rule):
          if fobos.has_option(rule,'quiet'):
            quiet = fobos.getboolean(rule,'quiet')
          else:
            quiet = cliargs.quiet
          for rul in fobos.options(rule):
            if rul.startswith('rule'):
              if not quiet:
                print(fobos_colors.bld+'   Command => '+fobos.get(rule,rul)+fobos_colors.end)
              result = syswork(fobos.get(rule,rul))
              if result[0] != 0:
                print(fobos_colors.red+result[1]+fobos_colors.end)
                sys.exit(1)
          sys.exit(0)
        else:
          print(fobos_colors.red+'Error: the rule "'+cliargs.execute+'" is not defined into the fobos file. Defined rules are:'+fobos_colors.end)
          rules_list(cliargs=cliargs,fobos=fobos,txtcolor=fobos_colors.red,colorend=fobos_colors.end)
          sys.exit(1)
    if cliargs.lmodes:
      if fobos.has_option('modes','modes'):
        print(fobos_colors.bld+'The fobos file defines the following modes:'+fobos_colors.end)
        modes_list(fobos=fobos,txtcolor=fobos_colors.bld,colorend=fobos_colors.end)
        #for m in fobos.get('modes','modes').split():
          #print fobos_colors.bld+'  - "'+m+'"'+fobos_colors.end
        sys.exit(0)
      else:
        print(fobos_colors.red+'Error: no modes are defined into the fobos file!'+fobos_colors.end)
        sys.exit(1)
    section = False
    if fobos.has_option('modes','modes'):
      if cliargs.mode:
        if cliargs.mode in fobos.get('modes','modes'):
          section = cliargs.mode
        else:
          print(fobos_colors.red+'Error: the mode "'+cliargs.mode+'" is not defined into the fobos file. Defined modes are:'+fobos_colors.end)
          modes_list(fobos=fobos,txtcolor=fobos_colors.red,colorend=fobos_colors.end)
          #for m in fobos.get('modes','modes').split():
            #print fobos_colors.red+'  - "'+m+'"'+fobos_colors.end
          sys.exit(1)
      else:
        section = fobos.get('modes','modes').split()[0] # first mode selected
    if not section:
      if fobos.has_section('default'):
        section = 'default'
      else:
        print(fobos_colors.red+'Error: fobos file has not "modes" section neither "default" one'+fobos_colors.end)
        sys.exit(1)
    # setting options from template-mode if used
    if fobos.has_option(section,'template'):
      if fobos.has_section(fobos.get(section,'template')):
        for item in fobos.items(fobos.get(section,'template')):
          fobos.set(section,item[0],item[1])
      else:
        print(fobos_colors.red+'Error: mode "'+section+'" uses as template the mode "'+fobos.get(section,'template')+'" that is NOT defined'+fobos_colors.end)
        sys.exit(1)
    # setting cliargs options accordingly to fobos one
    for item in fobos.items(section):
      if item[0] in cliargs_dict:
        item_value = item[1]
        if len(local_variables)>0:
          # the fobos defines some local variables: parsing the opstions for local variables expansion
          for key, value in local_variables.iteritems():
            if key in item_value:
              item_value = item_value.replace(key,value)
        if type(cliargs_dict[item[0]])==type(False):
          setattr(cliargs,item[0],fobos.getboolean(section,item[0]))
        elif type(cliargs_dict[item[0]])==type(1):
          setattr(cliargs,item[0],int(item[1]))
        elif type(cliargs_dict[item[0]])==type([]):
          setattr(cliargs,item[0],item[1].split())
        else:
          setattr(cliargs,item[0],item_value)
    for item in cliargs_dict:
      if item in ['cflags','lflags','preproc']:
        val_cli   = cliargs_dict[item]
        val_fobos = getattr(cliargs,item)
        if item == 'cflags':
          if val_cli == '-c':
            match = re.search(r'(-c\s+|-c$)',val_fobos)
            if match:
              val_cli ='' # avoid multiple -c flags
        if val_fobos and val_cli:
          setattr(cliargs,item,val_fobos+' '+val_cli)

# main loop
if __name__ == '__main__':
  __cliargs__ = __cliparser__.parse_args()
  if __cliargs__.fobos:
    inquire_fobos(cliargs=__cliargs__,fobosfile=__cliargs__.fobos)
  else:
    inquire_fobos(cliargs=__cliargs__)
  if __cliargs__.which=='clean':
    __cliargs__.build_dir = os.path.normpath(__cliargs__.build_dir)+"/"
    __cliargs__.mod_dir   = os.path.normpath(__cliargs__.mod_dir)+"/"
    __cliargs__.obj_dir   = os.path.normpath(__cliargs__.obj_dir)+"/"
    __cleaner__=Cleaner(build_dir=__cliargs__.build_dir,obj_dir=__cliargs__.obj_dir,mod_dir=__cliargs__.mod_dir,target=__cliargs__.target,output=__cliargs__.output,mklib=__cliargs__.mklib,colors=__cliargs__.colors)
    # clean project
    if not __cliargs__.only_obj and not __cliargs__.only_target:
      __cleaner__.clean_mod()
      __cleaner__.clean_obj()
      __cleaner__.clean_target()
    if __cliargs__.only_obj:
      __cleaner__.clean_mod()
      __cleaner__.clean_obj()
    if __cliargs__.only_target:
      __cleaner__.clean_target()
  elif __cliargs__.which=='build':
    __cliargs__.src        = os.path.normpath(__cliargs__.src)+"/"
    __cliargs__.build_dir  = os.path.normpath(__cliargs__.build_dir)+"/"
    __cliargs__.mod_dir    = os.path.normpath(__cliargs__.mod_dir)+"/"
    __cliargs__.obj_dir    = os.path.normpath(__cliargs__.obj_dir)+"/"
    __extensions_inc__    += __cliargs__.inc
    __extensions_parsed__ += __extensions_inc__
    if len(__cliargs__.pfm_ext)>0:
      __extensions_parsed__ += __cliargs__.pfm_ext
    __builder__=Builder(compiler=__cliargs__.compiler,fc=__cliargs__.fc,modsw=__cliargs__.modsw,mpi=__cliargs__.mpi,cflags=__cliargs__.cflags,lflags=__cliargs__.lflags,libs=__cliargs__.libs,dinc=__cliargs__.include,preproc=__cliargs__.preproc,build_dir=__cliargs__.build_dir,obj_dir=__cliargs__.obj_dir,mod_dir=__cliargs__.mod_dir,quiet=__cliargs__.quiet,colors=__cliargs__.colors,jobs=__cliargs__.jobs,preform=__cliargs__.preform,pfm_dir=__cliargs__.pfm_dir,pfm_ext=__cliargs__.pfm_ext)
    __pfiles__ = [] # main parsed files list
    # parsing files loop
    for root, subFolders, files in os.walk(__cliargs__.src):
      for filename in files:
        if any(os.path.splitext(os.path.basename(filename))[1]==ext for ext in __extensions_parsed__):
          if os.path.basename(filename) not in [os.path.basename(exc) for exc in __cliargs__.exclude]:
            file = os.path.join(root, filename)
            pfile = ParsedFile(name=file)
            pfile.parse()
            __pfiles__.append(pfile)
    # building dependencies hierarchy
    dependency_hiearchy(builder=__builder__,pfiles=__pfiles__)
    # saving makefile if requested
    if __cliargs__.makefile:
      # initializing makefile
      with open(__cliargs__.makefile, "w") as __mk_file__:
        __mk_file__.writelines("#!/usr/bin/make\n")
        __mk_file__.writelines("\n")
        __mk_file__.writelines("#main building variables\n")
        __mk_file__.writelines("DSRC    = "+__cliargs__.src+"\n")
        __mk_file__.writelines("DOBJ    = "+os.path.normpath(__builder__.obj_dir)+"/\n")
        __mk_file__.writelines("DMOD    = "+os.path.normpath(__builder__.mod_dir)+"/\n")
        __mk_file__.writelines("VPATH   = $(DSRC) $(DOBJ) $(DMOD)"+"\n")
        __mk_file__.writelines("DEXE    = "+os.path.normpath(__builder__.build_dir)+"/\n")
        __mk_file__.writelines("MKDIRS  = $(DOBJ) $(DMOD) $(DEXE)"+"\n")
        __mk_file__.writelines("LIBS    ="+"".join(" "+l for l in __builder__.libs)+"\n")
        __mk_file__.writelines("FC      = "+__builder__.fcs+"\n")
        __mk_file__.writelines("OPTSC   = "+__builder__.cflags+" "+__builder__.modsw+__builder__.mod_dir+"\n")
        __mk_file__.writelines("OPTSL   = "+__builder__.lflags+" "+__builder__.modsw+__builder__.mod_dir+"\n")
        __mk_file__.writelines("PREPROC = "+__builder__.preproc+"\n")
        __mk_file__.writelines("LCEXES  = $(shell echo $(EXES) | tr '[:upper:]' '[:lower:]')\n")
        __mk_file__.writelines("EXESPO  = $(addsuffix .o,$(LCEXES))\n")
        __mk_file__.writelines("EXESOBJ = $(addprefix $(DOBJ),$(EXESPO))\n")
        __mk_file__.writelines("\n")
        __mk_file__.writelines("#auxiliary variables\n")
        __mk_file__.writelines('COTEXT  = "Compiling $(<F)"\n')
        __mk_file__.writelines('LITEXT  = "Assembling $@"\n')
        __mk_file__.writelines("\n")
        __mk_file__.writelines("#building rules \n")
        # linking rules
        for pfile in __pfiles__:
          save_target_rule = False
          if pfile.program:
            save_target_rule = True
          elif __cliargs__.target:
            if os.path.basename(__cliargs__.target)==os.path.basename(pfile.name):
              save_target_rule = True
          if save_target_rule:
            __mk_file__.writelines("$(DEXE)"+pfile.basename.upper()+": $(MKDIRS) "+"$(DOBJ)"+pfile.basename.lower()+".o\n")
            __mk_file__.writelines("\t@rm -f $(filter-out $(DOBJ)"+pfile.basename.lower()+".o,$(EXESOBJ))\n")
            __mk_file__.writelines("\t@echo $(LITEXT)\n")
            __mk_file__.writelines("\t@$(FC) $(OPTSL) $(PREPROC) $(DOBJ)*.o $(LIBS) -o $@\n")
            __mk_file__.writelines("EXES := $(EXES) "+pfile.basename.upper()+"\n")
            __mk_file__.writelines("\n")
      # compiling rules
      for pfile in __pfiles__:
        pfile.save_makefile(makefile=__cliargs__.makefile,builder=__builder__)
      # phony auxiliary rules
      with open(__cliargs__.makefile, "a") as __mk_file__:
        __mk_file__.writelines("#phony rules \n")
        __mk_file__.writelines(".PHONY : $(MKDIRS)\n")
        __mk_file__.writelines("$(MKDIRS):\n")
        __mk_file__.writelines("\t@mkdir -p $@\n")
        __mk_file__.writelines(".PHONY : cleanobj\n")
        __mk_file__.writelines("cleanobj:\n")
        __mk_file__.writelines("\t@echo deleting objects\n")
        __mk_file__.writelines("\t@rm -fr $(DOBJ)\n")
        __mk_file__.writelines(".PHONY : cleanmod\n")
        __mk_file__.writelines("cleanmod:\n")
        __mk_file__.writelines("\t@echo deleting mods\n")
        __mk_file__.writelines("\t@rm -fr $(DMOD)\n")
        __mk_file__.writelines(".PHONY : cleanexe\n")
        __mk_file__.writelines("cleanexe:\n")
        __mk_file__.writelines("\t@echo deleting exes\n")
        __mk_file__.writelines("\t@rm -f $(addprefix $(DEXE),$(EXES))\n")
        __mk_file__.writelines(".PHONY : clean\n")
        __mk_file__.writelines("clean: cleanobj cleanmod\n")
        __mk_file__.writelines(".PHONY : cleanall\n")
        __mk_file__.writelines("cleanall: clean cleanexe\n")
      sys.exit(0)
    # compiling independent files that are libraries of procedures not contained into a module (old Fortran style)
    __nomodlibs__ = []
    for pfile in __pfiles__:
      if pfile.nomodlib:
        __builder__.build(file_to_build=pfile)
        __nomodlibs__.append(pfile.basename+".o")
    # building target or all programs found
    for pfile in __pfiles__:
      if __cliargs__.target:
        if os.path.basename(__cliargs__.target)==os.path.basename(pfile.name):
          print(__builder__.colors.bld+__builder__.verbose()+__builder__.colors.end)
          if pfile.program:
            remove_other_main(builder=__builder__,pfiles=__pfiles__,mysefl=pfile)
          __builder__.build(file_to_build=pfile,output=__cliargs__.output,nomodlibs=__nomodlibs__,mklib=__cliargs__.mklib)
          if __cliargs__.log:
            pfile.save_build_log(builder=__builder__)
      else:
        if pfile.program:
          print(__builder__.colors.bld+__builder__.verbose()+__builder__.colors.end)
          remove_other_main(builder=__builder__,pfiles=__pfiles__,mysefl=pfile)
          __builder__.build(file_to_build=pfile,output=__cliargs__.output,nomodlibs=__nomodlibs__)
          if __cliargs__.log:
            pfile.save_build_log(builder=__builder__)
