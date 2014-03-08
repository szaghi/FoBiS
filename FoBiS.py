#!/usr/bin/env python
"""
FoBiS.py, Fortran Building System for poor men
"""
__appname__ = 'FoBiS.py'
__version__ ="0.0.1"
__author__  = 'Stefano Zaghi'
# modules loading
try:
  import sys,os,time,argparse,shutil,ConfigParser,operator
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
buildparser.add_argument('-o',help='Specify the output file name is used with -target switch [default: basename of target]',required=False,action='store',default=None)
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
class Colors(object):
  """
  Colors is an object that handles colors of shell prints, its attributes and methods.
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
class Builder(object):
  """
  Builder is an object that handles the building system, its attributes and methods.
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
               dexe     = "./",    # directory containing compiled executable files
               quiet    = False,   # make printings less verbose than default
               colors   = False,   # make printings colored
               jobs     = 1):      # concurrent compiling jobs
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
    self.quiet    = quiet
    self.jobs     = jobs
    self.colors   = Colors()
    if not colors:
      self.colors.disable()
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
    if not os.path.exists(self.dmod):
      os.makedirs(self.dmod)
    if not os.path.exists(self.dobj):
      os.makedirs(self.dobj)
    if not os.path.exists(self.dexe):
      os.makedirs(self.dexe)
  def compile_recurive(self,pfile):
    """
    The method compile compiles pfile and all its dependencies if necessary.
    """
    if not pfile.include:
     if pfile.to_compile:
       if len(pfile.pfile_dep)>0:
         if pfile.target and self.jobs>1:
           print self.colors.bld+"Using "+str(self.jobs)+" concurrent processes for comiling "+pfile.name+" dependencies"+self.colors.end
           pool = Pool(processes=self.jobs)
           for dep in pfile.pfile_dep:
             pool.apply_async(self.compile(pfile=dep))
           pool.close()
           pool.join()
         else:
           for dep in pfile.pfile_dep:
             self.compile(pfile=dep)
       if len(self.dinc)>0:
         comp_cmd = self.cmd_comp+" "+"".join(["-I"+s+" " for s in self.dinc])+pfile.name+" -o "+self.dobj+pfile.basename+".o"
       else:
         comp_cmd = self.cmd_comp+" "                                         +pfile.name+" -o "+self.dobj+pfile.basename+".o"
       if self.quiet:
         print self.colors.bld+"Compiling "+pfile.name+self.colors.end
       else:
         print self.colors.bld+comp_cmd+self.colors.end
       os.system(comp_cmd)
       pfile.to_compile = False
  def compile(self,pfile):
    """
    The method compile compiles pfile and all its dependencies if necessary.
    """
    if not pfile.include:
     if pfile.to_compile:
       if len(self.dinc)>0:
         comp_cmd = self.cmd_comp+" "+"".join(["-I"+s+" " for s in self.dinc])+pfile.name+" -o "+self.dobj+pfile.basename+".o"
       else:
         comp_cmd = self.cmd_comp+" "                                         +pfile.name+" -o "+self.dobj+pfile.basename+".o"
       if self.quiet:
         print self.colors.bld+"Compiling "+pfile.name+self.colors.end
       else:
         print self.colors.bld+comp_cmd+self.colors.end
       os.system(comp_cmd)
       pfile.to_compile = False
  def build(self,pfile,output=None):
    """
    The method build builds current file.
    """
    pfile.to_compile = True
    pfile.target = True
    #Ndep = sum(1 for dep in pfile.pfile_dep_all if dep.to_compile) # number of dependencies that must be compiled
    for dep in pfile.pfile_dep_all:
      if dep.to_compile and dep != pfile:
        self.compile(pfile=dep)
    self.compile(pfile=pfile)
    if pfile.program:
      objs = pfile.obj_dependencies()
      if output:
        exe=output
      else:
        exe=pfile.basename
      if len(self.libs)>0:
        link_cmd = self.cmd_link+" "+"".join([self.dobj+s+" " for s in objs])+"".join([s+" " for s in self.libs])+"-o "+self.dexe+exe
      else:
        link_cmd = self.cmd_link+" "+"".join([self.dobj+s+" " for s in objs])                                    +"-o "+self.dexe+exe
      if self.quiet:
        print self.colors.red+"Linking "+self.builder.dexe+self.basename+self.colors.end
      else:
        print self.colors.red+link_cmd+self.colors.end
      os.system(link_cmd)
class Dependency(object):
  """
  Dependency is an object that handles a single file dependency, its attributes and methods.
  """
  def __init__(self,
               type = "",  # type of dependency: "module" or "include" type
               name = "",  # name of depedency: module name for "use" type or file name for include type
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
               target       = False,     # flag for checking if the file is a target to be built
               output       = None):     # eventual user-supplied output file name
    self.name         = name
    self.program      = program
    self.module       = module
    self.include      = include
    self.nomodlib     = nomodlib
    self.to_compile   = to_compile
    self.target       = target
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
    log_file.writelines(" Hierarchical dependencies list of: "+self.name+"\n")
    for dep in self.pfile_dep:
      log_file.writelines("   "+dep.name+"\n")
      log_file.writelines(dep.str_dependencies(pref="     "))
    log_file.writelines(" Complete ordered dependencies list of: "+self.name+"\n")
    for dep in self.pfile_dep_all:
      log_file.writelines("  "+dep.name+"\n")
    log_file.writelines(" Builder options"+"\n")
    log_file.writelines("   Compiled-objects .o   directory: "+builder.dobj+"\n")
    log_file.writelines("   Compiled-objects .mod directory: "+builder.dmod+"\n")
    log_file.writelines("   Executable directory:            "+builder.dexe+"\n")
    log_file.writelines("   Compiler used:                   "+builder.compiler+"\n")
    log_file.writelines("   Compilation flags:               "+builder.cflags+"\n")
    log_file.writelines("   Linking     flags:               "+builder.lflags+"\n")
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
  def check_compile(self,dobj):
    """
    The method check_compile checks if self must be compiled.
    """
    if not self.include:
      # verifying if dependencies are up-to-date
      for dep in self.pfile_dep_all:
        if not dep.include:
          obj = dobj+dep.basename+".o"
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
            obj = dobj+self.basename+".o"
            # verifying if dep is up-to-date
            if os.path.exists(obj):
              if os.path.getmtime(obj) < os.path.getmtime(dep.name):
                # found an include that is newer than self-compiled-object, thus self must be compiled
                self.to_compile = True
      # verifying if self is up-to-date
      if not self.to_compile:
        obj = dobj+self.basename+".o"
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
    pfile.check_compile(dobj=builder.dobj)
    # correct the list ordering accordingly to indirect dependency
    for dep in pfile.pfile_dep_all:
      for other_dep in pfile.pfile_dep_all:
        if other_dep != dep:
          if dep in other_dep.pfile_dep_all:
            dep.order = other_dep.order+1
    pfile.pfile_dep_all.sort(key=operator.attrgetter('order'),reverse=True)
def remove_other_main(builder,pfiles,me):
  """
  The function remove_other_main removes all compiled objects of other program than the current target under building.
  """
  for pfile in pfiles:
    if pfile.program and pfile.name!=me.name:
      if os.path.exists(builder.dobj+pfile.basename+".o"):
        os.remove(builder.dobj+pfile.basename+".o")
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
      elif item[0]=='src':
        cliargs.src = item[1]
      elif item[0]=='colors':
        cliargs.colors = fobos.getboolean('builder',item[0])
      elif item[0]=='quiet':
        cliargs.quiet = fobos.getboolean('builder',item[0])
      elif item[0]=='jobs':
        cliargs.j = int(item[1])
    for item in fobos.items('files'):
      if item[0]=='target':
        cliargs.target = item[1]
      elif item[0]=='output':
        cliargs.o = item[1]
      elif item[0]=='log':
        cliargs.log = fobos.getboolean('files',item[0])
# main loop
if __name__ == '__main__':
  cliargs = cliparser.parse_args()
  if cliargs.f:
    inquire_fobos(cliargs=cliargs,filename=cliargs.f)
  else:
    inquire_fobos(cliargs=cliargs)
  if cliargs.which=='clean':
    # cleaning project
    colors = Colors()
    if not cliargs.colors:
      colors.disable()
    print colors.red+"Removing "+cliargs.dobj+" and "+cliargs.dmod+colors.end
    if os.path.exists(cliargs.dobj):
      shutil.rmtree(cliargs.dobj)
    if os.path.exists(cliargs.dmod):
      shutil.rmtree(cliargs.dmod)
  elif cliargs.which=='build':
    builder=Builder(compiler=cliargs.compiler,fc=cliargs.fc,modsw=cliargs.modsw,mpi=cliargs.mpi,cflags=cliargs.cflags,lflags=cliargs.lflags,libs=cliargs.libs,dinc=cliargs.I,dobj=cliargs.dobj,dmod=cliargs.dmod,dexe=cliargs.dexe,quiet=cliargs.quiet,colors=cliargs.colors,jobs=cliargs.j)
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
    nomodlibs = ['']
    for pfile in pfiles:
      if pfile.nomodlib:
        builder.compile(pfile=pfile)
        nomodlibs.append(pfile.basename+".o")
    # building target or all programs found
    for pfile in pfiles:
      if cliargs.target:
        if os.path.basename(cliargs.target)==os.path.basename(pfile.name):
          if pfile.program:
            remove_other_main(builder=builder,pfiles=pfiles,me=pfile)
          builder.build(pfile=pfile,output=cliargs.o)
          if cliargs.log:
            pfile.save_build_log(builder=builder)
      else:
        if pfile.program:
          remove_other_main(builder=builder,pfiles=pfiles,me=pfile)
          builder.build(pfile=pfile,output=cliargs.o)
          if cliargs.log:
            pfile.save_build_log(builder=builder)
