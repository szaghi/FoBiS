#!/usr/bin/env python
"""
FoBiS.py, Fortran Building System for poor men
"""
__appname__ = 'FoBiS.py'
__version__ ="0.0.1"
__author__  = 'Stefano Zaghi'
# modules loading
try:
  import sys,os,time,argparse,shutil,ConfigParser
  from multiprocessing import Pool
except:
  sys.exit(1)
try:
  import re
except:
  print """
        The regular expression module 're' not found
        """
  sys.exit(1)
# setting CLI
cliparser = argparse.ArgumentParser(prog=__appname__,description='FoBiS.py, Fortran Building System for poor men')
cliparser.add_argument('-v','--version',action='version',help='Show version',version='%(prog)s '+__version__)
clisubparsers = cliparser.add_subparsers(title='Commands',description='Valid commands')
buildparser = clisubparsers.add_parser('build',help='Build all programs found or a specific target')
buildparser.set_defaults(which='build')
buildparser.add_argument('-f',help='Specify a "fobos" file named differently from "fobos"',required=False,action='store')
buildparser.add_argument('-colors',help='Activate colors in shell prints [default: no colors]',required=False,action='store_true',default=False)
buildparser.add_argument('-log',help='Activate the creation of a log file [default: no log file]',required=False,action='store_true',default=False)
buildparser.add_argument('-quiet',help='Less verbose than default',required=False,action='store_true',default=False)
buildparser.add_argument('-j',help='Specify the number of concurrent jobs used for compiling dependencies (enable parallel, multiprocessing buildings useful on parallel architectures for speedup compiling)',required=False,action='store',default=1,type=int)
buildparser.add_argument('-exclude',help='Exclude a list of files from the building process',required=False,action='store',nargs='+',default=[])
buildparser.add_argument('-target',help='Build a specific file [default: all programs found]',required=False,action='store')
buildparser.add_argument('-o',help='Specify the output file name is used with -target switch [default: basename of target]',required=False,action='store')
buildparser.add_argument('-compiler',help='Compiler used: Intel, GNU, IBM, PGI, g95 or Custom [default: Intel]',required=False,action='store',default='Intel')
buildparser.add_argument('-fc',help='Specify the Fortran compiler statement, necessary for custom compiler specification (-compiler Custom)',required=False,action='store',default='')
buildparser.add_argument('-modsw',help='Specify the switch for specifying the module searching path, necessary for custom compiler specification (-compiler Custom)',required=False,action='store',default='')
buildparser.add_argument('-mpi',help='Use MPI enabled version of compiler',required=False,action='store_true',default=False)
buildparser.add_argument('-cflags',help='Compilation flags [default: -c -cpp]',required=False,action='store',default='-c -cpp')
buildparser.add_argument('-lflags',help='Linking flags',required=False,action='store',default='')
buildparser.add_argument('-libs',help='List of external libraries used',required=False,action='store',nargs='+',default=[])
buildparser.add_argument('-I',help='List of directories for searching included files',required=False,action='store',nargs='+',default=[])
buildparser.add_argument('-dobj',help='Directory containing compiled objects [default: ./obj/]',required=False,action='store',default='./obj/')
buildparser.add_argument('-dmod',help='Directory containing .mod files of compiled objects [default: ./mod/]',required=False,action='store',default='./mod/')
buildparser.add_argument('-dexe',help='Directory containing executable objects [default: ./]',required=False,action='store',default='./')
buildparser.add_argument('-src',help='Root-directory of source files [default: ./]',required=False,action='store',default='./')
cleanparser = clisubparsers.add_parser('clean',help='Clean project: completely remove DOBJ and DMOD directories... use carefully')
cleanparser.set_defaults(which='clean')
cleanparser.add_argument('-f',help='Specify a "fobos" file named differently from "fobos"',required=False,action='store')
cleanparser.add_argument('-colors',help='Activate colors in shell prints [default: no colors]',required=False,action='store_true',default=False)
cleanparser.add_argument('-dobj',help='Directory containing compiled objects [default: ./obj/]',required=False,action='store',default='./obj/')
cleanparser.add_argument('-dmod',help='Directory containing .mod files of compiled objects [default: ./mod/]',required=False,action='store',default='./mod/')
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
__extensions_inc__    = [".inc",".INC"]
__extensions_parsed__ = __extensions_old__ + __extensions_modern__ + __extensions_inc__
# classes definitions
class bcolors(object):
  """
  bcolors is an object that handles colors of shell prints, its attributes and methods.
  """
  def __init__(self,
               red = '\033[1;31m',
               bld = '\033[1m',
               err = '\033[91m'):
    self.red = red
    self.bld = bld
    self.err = err
    self.end = '\033[0m'
  def disable(self):
    self.red = ''
    self.bld = ''
    self.err = ''
    self.end = ''
class builder(object):
  """
  builder is an object that handles a single program building system, its attributes and methods.
  """
  def __init__(self,
               compiler = "Intel", # compiler used
               fc       = "",      # custom compiler statement
               modsw    = "",      # custom compiler switch for modules searching path
               mpi      = False,   # use MPI enabled version of compiler
               cflags   = "-c",    # compilation flags
               lflags   = "",      # linking flags
               libs     = [],      # list of external libraries
               dinc     = [],      # list of directories for searching included files
               dmod     = "./",    # directory containing .mod files
               dobj     = "./",    # directory containing compiled object files
               dexe     = "./"):   # directory containing compiled executable files
    self.compiler = compiler
    self.fc       = fc
    self.modsw    = modsw
    self.mpi      = mpi
    self.cflags   = cflags
    self.lflags   = lflags
    self.libs     = libs
    self.dinc     = dinc
    self.dmod     = dmod
    self.dobj     = dobj
    self.dexe     = dexe
    if compiler.lower() == "gnu":
      if mpi:
        self.cmd_comp = "mpif90 "+self.cflags+" -J"+self.dmod
        self.cmd_link = "mpif90 "+self.lflags+" -J"+self.dmod
      else:
        self.cmd_comp = "gfortran "+self.cflags+" -J"+self.dmod
        self.cmd_link = "gfortran "+self.lflags+" -J"+self.dmod
    elif compiler.lower() == "intel":
      if mpi:
        self.cmd_comp = "mpif90 "+self.cflags+" -module "+self.dmod
        self.cmd_link = "mpif90 "+self.lflags+" -module "+self.dmod
      else:
        self.cmd_comp = "ifort "+self.cflags+" -module "+self.dmod
        self.cmd_link = "ifort "+self.lflags+" -module "+self.dmod
    elif compiler.lower() == "custom":
      self.cmd_comp = self.fc+" "+self.cflags+" "+self.modsw+" "+self.dmod
      self.cmd_link = self.fc+" "+self.lflags+" "+self.modsw+" "+self.dmod
  def compile(self,filename):
    if not os.path.exists(self.dmod):
      os.makedirs(self.dmod)
    if not os.path.exists(self.dobj):
      os.makedirs(self.dobj)
    basename = os.path.splitext(os.path.basename(filename))[0]
    if self.dinc.__len__()>0:
      comp_cmd = self.cmd_comp+" "+"".join(["-I"+s+" " for s in self.dinc])+filename+" -o "+self.dobj+basename+".o"
    else:
      comp_cmd = self.cmd_comp+" "                                         +filename+" -o "+self.dobj+basename+".o"
    os.system(comp_cmd)
    return comp_cmd
  def link(self,filename,objs,output=None):
    if not os.path.exists(self.dexe):
      os.makedirs(self.dexe)
    basename = os.path.splitext(os.path.basename(filename))[0]
    if output:
      exe=output
    else:
      exe=basename
    if self.libs.__len__>0:
      link_cmd = self.cmd_link+" "+"".join([self.dobj+s+" " for s in objs])+"".join([s+" " for s in self.libs])+"-o "+self.dexe+exe
    else:
      link_cmd = self.cmd_link+" "+"".join([self.dobj+s+" " for s in objs])                                    +"-o "+self.dexe+exe
    os.system(link_cmd)
    return link_cmd
class dependency(object):
  """
  dependency is an object that handles a single file dependency, its attributes and methods.
  """
  def __init__(self,
               dep_type = "",  # type of dependency: "module" or "include" type
               dep_name = "",  # name of depedency: module name for "use" type or file name for include type
               dep_file = ""): # file name containing module in the case of "use" type
    self.dep_type = dep_type
    self.dep_name = dep_name
    self.dep_file = dep_file
class parsed_file(object):
  """
  parsed_file is an object that handles a single parsed file, its attributes and methods.
  """
  def __init__(self,
               name,                     # file name
               program      = False,     # flag for checking if the file is a program
               module       = False,     # flag for checking if the file is a modules file
               include      = False,     # flag for checking if the file is an include-dependency
               nomodlib     = False,     # flag for checking if the file is library of procedures with an enclosing module (old Fortran style)
               to_compile   = False,     # flag for checking if the file must be compiled
               quiet        = False,     # make printings less verbose than default
               colored      = False,     # make printings colored
               builder      = builder(), # debug builder
               module_names = [],        # in case the file contains modules definition, this is the list of modules defined
               dependencies = [],        # dependency list
               pfile_dep    = [],        # parsed file dependent list
               jobs         = 1):        # concurrent compiling jobs
    self.name         = name
    self.program      = program
    self.module       = module
    self.include      = include
    self.nomodlib     = nomodlib
    self.to_compile   = to_compile
    self.quiet        = quiet
    self.builder      = builder
    self.module_names = module_names
    self.dependencies = dependencies
    self.pfile_dep    = pfile_dep
    self.jobs         = jobs
    self.basename     = os.path.splitext(os.path.basename(self.name))[0]
    self.timestamp    = os.path.getmtime(self.name)
    self.bcolors      = bcolors()
    if not colored:
      self.bcolors.disable()
  def parse(self):
    """
    The method parse parses the fortran source code file.
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
            dep = dependency(dep_type="module",dep_name=matching.group('name'))
            self.dependencies.append(dep)
      matching = re.match(regex_f95_include,line)
      if matching:
        if not re.match(regex_f95_mpifh,line):
          dep = dependency(dep_type="include",dep_name=matching.group('name'))
          self.dependencies.append(dep)
    ffile.close()
    if not self.program and not self.module:
      if  os.path.splitext(os.path.basename(self.name))[1] not in __extensions_inc__:
        self.nomodlib = True
  def save_build_log(self):
    """
    The method save_build_log save a log file containing information about the building options used.
    """
    log_file = open("build_"+self.basename+".log", "w")
    log_file.writelines(" Building dependency of: "+self.name+"\n")
    for dep in self.pfile_dep:
      log_file.writelines("   "+dep.name+"\n")
      log_file.writelines(dep.str_dependencies(pref="     "))
    log_file.writelines(" Compiled-objects .o   directory: "+self.builder.dobj+"\n")
    log_file.writelines(" Compiled-objects .mod directory: "+self.builder.dmod+"\n")
    log_file.writelines(" Executable directory:            "+self.builder.dexe+"\n")
    log_file.writelines(" Compiler used:                   "+self.builder.compiler+"\n")
    log_file.writelines(" Compilation flags:               "+self.builder.cflags+"\n")
    log_file.writelines(" Linking     flags:               "+self.builder.lflags+"\n")
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
  def obj_dependencies(self,obj_dep=[]):
    """
    The method obj_dependencies create a list containing the dependencies object files list.
    """
    if self.pfile_dep.__len__()>0:
      for dep in self.pfile_dep:
        if not dep.include:
          dep.obj_dependencies(obj_dep)
          obj_dep.append(dep.basename+".o")
    obj_dep.append(self.basename+".o")
    return list(set(obj_dep))
  def check_compile(self):
    """
    The method check_compile checks if self must be set to be compiled.
    """
    if not self.include:
      # verifiyng if self must be compiled
      if self.pfile_dep.__len__()>0:
        # verifying if any depencies must be compiled
        for dep in self.pfile_dep:
          if not dep.include:
            obj = dep.builder.dobj+dep.basename+".o"
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
              obj = self.builder.dobj+self.basename+".o"
              # verifying if dep is up-to-date
              if os.path.exists(obj):
                if os.path.getmtime(obj) < os.path.getmtime(dep.name):
                  # found an include that is newer than self-compiled-object, thus self must be compiled
                  self.to_compile = True
      # verifying if self is up-to-date
      if not self.to_compile:
        obj = self.builder.dobj+self.basename+".o"
        if os.path.exists(obj):
          if os.path.getmtime(obj) < self.timestamp:
            # the compiled object is out-of-date, thus self must be compiled
            self.to_compile = True
        else:
          # compiled object is absent, thus self must be compiled
          self.to_compile = True
  def compile(self,target=False):
    """
    The method compile compiles current file and all its dependencies if necessary.
    """
    if not self.include:
      if self.to_compile:
        if self.pfile_dep.__len__()>0:
          if target and self.jobs>1:
            pool = Pool(processes=self.jobs)
            for dep in self.pfile_dep:
              pool.apply_async(dep.compile())
            pool.close()
            pool.join()
          else:
            for dep in self.pfile_dep:
              dep.compile()
        if self.quiet:
          print self.bcolors.bld+"Compiling "+self.name+self.bcolors.end
          self.builder.compile(filename=self.name)
        else:
          print self.bcolors.bld+self.builder.compile(filename=self.name)+self.bcolors.end
        self.to_compile = False
  def build(self,output=None):
    """
    The method build builds current file.
    """
    self.to_compile = True
    self.compile(target=True)
    if self.program:
      objs = self.obj_dependencies(obj_dep=[])
      if self.quiet:
        print self.bcolors.red+"Linking "+self.builder.dexe+self.basename+self.bcolors.end
        self.builder.link(filename=self.name,objs=objs,output=output)
      else:
        print self.bcolors.red+self.builder.link(filename=self.name,objs=objs,output=output)+self.bcolors.end
# auxiliary functions definitions
def module_is_in(pfiles,module):
  """
  The function module_is_in find the parsed file containing the desidered module.
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
def check_compiling_dependency(pfiles,depdump=False):
  """
  The function check_compiling_dependency refresh the compiling dependency list of the parsed files list.
  """
  for pfile in pfiles:
    pfile.check_compile()
  for pfile in pfiles:
    if any(pf.to_compile for pf in pfile.pfile_dep):
      pfile.to_compile = True
  if depdump:
    # saving compiling dependency dump to file
    dep_file = open("dependency_hierarchy.log","w")
    for pfile in pfiles:
      dep_file.writelines(" Building dependency of: "+pfile.name+"\n")
      for dep in pfile.pfile_dep:
        dep_file.writelines("   "+dep.name+"\n")
        dep_file.writelines(dep.str_dependencies(pref="     "))
    dep_file.close()
def remove_other_main(pfiles,me):
  """
  The function remove_other_main removes all compiled objects of other program than the current target under building.
  """
  for pfile in pfiles:
    if pfile.program and pfile.name!=me.name:
      if os.path.exists(pfile.builder.dobj+pfile.basename+".o"):
        os.remove(pfile.builder.dobj+pfile.basename+".o")
def inquire_fobos(cliargs,filename='fobos'):
  """
  The function inquiry_fobos checks if a file named 'fobos' is present in current working directory and, in case, parses it for CLI arguments overriding.
  """
  if os.path.exists(filename):
    fobos = ConfigParser.ConfigParser()
    fobos.read(filename)
    for item in fobos.items('builder'):
      if item[0]=='compiler':
        cliargs.compiler = item[1]
      elif item[0]=='fc':
        cliargs.fc = item[1]
      elif item[0]=='modsw':
        cliargs.modsw = item[1]
      elif item[0]=='mpi':
        cliargs.mpi = fobos.getboolean('builder',item[0])
      elif item[0]=='cflags':
        cliargs.cflags = item[1]
      elif item[0]=='lflags':
        cliargs.lflags = item[1]
      elif item[0]=='libs':
        cliargs.libs = item[1].split()
      elif item[0]=='dmod':
        cliargs.dmod = item[1]
      elif item[0]=='dobj':
        cliargs.dobj = item[1]
      elif item[0]=='dexe':
        cliargs.dexe = item[1]
    for item in fobos.items('general'):
      if item[0]=='src':
        cliargs.src = item[1]
      elif item[0]=='colors':
        cliargs.colors = fobos.getboolean('general',item[0])
      elif item[0]=='log':
        cliargs.log = fobos.getboolean('general',item[0])
      elif item[0]=='quiet':
        cliargs.quiet = fobos.getboolean('general',item[0])
      elif item[0]=='jobs':
        cliargs.j = int(item[1])
      elif item[0]=='target':
        cliargs.target = item[1]
      elif item[0]=='output':
        cliargs.o = item[1]
# main loop
if __name__ == '__main__':
  cliargs = cliparser.parse_args()
  if cliargs.f:
    inquire_fobos(cliargs=cliargs,filename=cliargs.f)
  else:
    inquire_fobos(cliargs=cliargs)
  if cliargs.which=='clean':
    # cleaning project
    colors = bcolors()
    if not cliargs.colors:
      colors.disable()
    print colors.red+"Removing "+cliargs.dobj+" and "+cliargs.dmod+colors.end
    if os.path.exists(cliargs.dobj):
      shutil.rmtree(cliargs.dobj)
    if os.path.exists(cliargs.dmod):
      shutil.rmtree(cliargs.dmod)
  elif cliargs.which=='build':
    pfiles = []
    # parsing files loop
    for root, subFolders, files in os.walk(cliargs.src):
      for filename in files:
        if any(os.path.splitext(os.path.basename(filename))[1]==ext for ext in __extensions_parsed__):
          if os.path.basename(filename) not in [os.path.basename(exc) for exc in cliargs.exclude]:
            file = os.path.join(root, filename)
            pfile = parsed_file(name=file,
                                quiet=cliargs.quiet,
                                colored=cliargs.colors,
                                jobs=cliargs.j,
                                builder=builder(compiler=cliargs.compiler,fc=cliargs.fc,modsw=cliargs.modsw,mpi=cliargs.mpi,cflags=cliargs.cflags,lflags=cliargs.lflags,libs=cliargs.libs,dinc=cliargs.I,dobj=cliargs.dobj,dmod=cliargs.dmod,dexe=cliargs.dexe))
            pfile.parse()
            pfiles.append(pfile)
    # building dependencies hierarchy
    for pfile in pfiles:
      pfile.pfile_dep = []
      for dep in pfile.dependencies:
        if dep.dep_type=="module":
          dep.dep_file,n = module_is_in(pfiles=pfiles,module=dep.dep_name)
          if n>-1:
            pfile.pfile_dep.append(pfiles[n])
          else:
            print pfile.bcolors.red+"Attention: the file '"+pfile.name+"' depends on '"+dep.dep_name+"' that is unreachable"+pfile.bcolors.end
            sys.exit(1)
        if dep.dep_type=="include":
          dep.dep_file,n = include_is_in(pfiles=pfiles,include=dep.dep_name)
          if n>-1:
            pfiles[n].program = False
            pfiles[n].module  = False
            pfiles[n].include = True
            pfile.pfile_dep.append(pfiles[n])
            if not os.path.dirname(pfiles[n].name) in pfile.builder.dinc:
              pfile.builder.dinc.append(os.path.dirname(pfiles[n].name))
          else:
            print pfile.bcolors.red+"Attention: the file '"+pfile.name+"' depends on '"+dep.dep_name+"' that is unreachable"+pfile.bcolors.end
            sys.exit(1)
    check_compiling_dependency(pfiles=pfiles)
    # compiling independent files that are libraries of procedures not contained into a module (old Fortran style)
    nomodlibs = ['']
    for pfile in pfiles:
      if pfile.nomodlib:
        pfile.compile()
        nomodlibs.append(pfile.basename+".o")
    # building target or all programs found
    for pfile in pfiles:
      if cliargs.target:
        if os.path.basename(cliargs.target)==os.path.basename(pfile.name):
          if pfile.program:
            remove_other_main(pfiles=pfiles,me=pfile)
          if cliargs.o:
            pfile.build(output=cliargs.o)
          else:
            pfile.build()
          if cliargs.log:
            pfile.save_build_log()
      else:
        if pfile.program:
          remove_other_main(pfiles=pfiles,me=pfile)
          pfile.build()
          if cliargs.log:
            pfile.save_build_log()
