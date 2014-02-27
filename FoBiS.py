#!/usr/bin/env python
"""
FoBiS.py, Fortran Building System for poor men
"""
__appname__ = 'FoBiS.py'
__version__ ="0.0.1"
__author__  = 'Stefano Zaghi'

# modules loading
try:
  import sys,os,time,argparse,shutil
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
buildparser.add_argument('-target',help='Build a specific file [default: all programs found]',required=False,action='store')
buildparser.add_argument('-compiler',help='Compiler used: Intel, GNU, IBM, PGI or g95 [default: Intel]',required=False,action='store',default='Intel')
buildparser.add_argument('-cflags',help='Compilation flags [default: -c -cpp]',required=False,action='store',default='-c -cpp')
buildparser.add_argument('-lflags',help='Linking flags',required=False,action='store',default='')
buildparser.add_argument('-libs',help='List of external libraries used',required=False,action='store',nargs='+',default=[''])
buildparser.add_argument('-dobj',help='Directory containing compiled objects [default: ./obj/]',required=False,action='store',default='./obj/')
buildparser.add_argument('-dmod',help='Directory containing .mod files of compiled objects [default: ./mod/]',required=False,action='store',default='./mod/')
buildparser.add_argument('-dexe',help='Directory containing executable objects [default: ./]',required=False,action='store',default='./')
buildparser.add_argument('-src',help='Root-directory of source files',required=True,action='store')
cleanparser = clisubparsers.add_parser('clean',help='Clean project: completely remove DOBJ and DMOD directories... use carefully')
cleanparser.set_defaults(which='clean')
cleanparser.add_argument('-dobj',help='Directory containing compiled objects [default: ./obj/]',required=False,action='store',default='./obj/')
cleanparser.add_argument('-dmod',help='Directory containing .mod files of compiled objects [default: ./mod/]',required=False,action='store',default='./mod/')

# definition of regular expressions
str_f95_apex       = r"('|"+r'")'
str_f95_kw_include = r"[Ii][Nn][Cc][Ll][Uu][Dd][Ee]"
str_f95_kw_module  = r"[Mm][Oo][Dd][Uu][Ll][Ee]"
str_f95_kw_program = r"[Pp][Rr][Oo][Gg][Rr][Aa][Mm]"
str_f95_kw_use     = r"[Uu][Ss][Ee]"
str_f95_name       = r"(?P<name>[a-zA-Z][a-zA-Z0-9_]*)"
str_f95_eol        = r"(?P<eol>\s*!.*|\s*)?$"
str_f95_mod_rename = r"(\s*,\s*[a-zA-Z][a-zA-Z0-9_]*\s*=>\s*[a-zA-Z][a-zA-Z0-9_]*)*"
str_f95_mod_only   = r"(\s*,\s*[Oo][Nn][Ll][Yy]\s*:\s*([a-zA-Z][a-zA-Z0-9_]*\s*=>\s*[a-zA-Z][a-zA-Z0-9_]*|[a-zA-Z][a-zA-Z0-9_]*))*"
str_f95_use_mod = (r"^(\s*)"          + # eventual initial white spaces
                   str_f95_kw_use     + # f95 keyword "use"
                   r"(\s+)"           + # 1 or more white spaces
                   str_f95_name       + # f95 construct name
                   r"(?P<mod_eol>"    +
                   r"(.*&.*|"         + # eventual splitted scope
                   str_f95_mod_only   + # f95 only access to module
                   str_f95_mod_rename + # eventual module entities renaming
                   str_f95_eol+"))")    # eventual eol white space and or comment
str_f95_include = (r"^(\s*|\#)"       + # eventual initial white spaces or "#" character
                   str_f95_kw_include + # f95 keyword "include"
                   r"(\s+)"           + # 1 or more white spaces
                   str_f95_apex       + # character "'" or '"'
                   r"(\s*)"           + # eventaul white spaces
                   r"(?P<name>.*)"    + # name of included file
                   r"(\s*)"           + # eventaul white spaces
                   str_f95_apex       + # character "'" or '"'
                   str_f95_eol)         # eventual eol white space and or comment
str_f95_module  = (r"^(\s*)"                               + # eventual initial white spaces
                   r"(?P<scplevel>"+str_f95_kw_module+r")" + # f95 keyword "module"
                   r"(\s+)"                                + # 1 or more white spaces
                   str_f95_name                            + # f95 construct name
                   str_f95_eol)                              # eventual eol white space and or comment
str_f95_program = (r"^(\s*)"                                + # eventual initial white spaces
                   r"(?P<scplevel>"+str_f95_kw_program+r")" + # f95 keyword "program"
                   r"(\s+)"                                 + # 1 or more white spaces
                   str_f95_name                             + # f95 construct name
                   str_f95_eol)                               # eventual eol white space and or comment
regex_f95_use_mod = re.compile(str_f95_use_mod)
regex_f95_include = re.compile(str_f95_include)
regex_f95_program = re.compile(str_f95_program)
regex_f95_module  = re.compile(str_f95_module)

__extensions_parsed__ = [".f",".f90",".f95",".f03",".f08",".f2k",".inc"]

# classes definitions
class builder:
  """
  builder is an object that handles a single program building system, its attributes and methods.
  """
  def __init__(self,
               compiler = "GNU", # compiler used
               cflags   = "-c",  # compilation flags
               lflags   = "",    # linking flags
               libs     = [],    # external libraries
               dmod     = "./",  # directory containing .mod files
               dobj     = "./",  # directory containing compiled object files
               dexe     = "./"): # directory containing compiled executable files
    self.compiler = compiler
    self.cflags   = cflags
    self.lflags   = lflags
    self.libs     = libs
    self.dmod     = dmod
    self.dobj     = dobj
    self.dexe     = dexe
    if compiler == "GNU":
      self.cmd_comp = "gfortran "+self.cflags+" -J"+self.dmod
      self.cmd_link = "gfortran "+self.lflags+" -J"+self.dmod
    elif compiler == "Intel":
      self.cmd_comp = "ifort "+self.cflags+" -module "+self.dmod
      self.cmd_link = "ifort "+self.lflags+" -module "+self.dmod
  def compile(self,filename):
    if not os.path.exists(self.dmod):
      os.makedirs(self.dmod)
    if not os.path.exists(self.dobj):
      os.makedirs(self.dobj)
    basename = os.path.splitext(os.path.basename(filename))[0]
    comp_cmd = self.cmd_comp+" "+filename+" -o "+self.dobj+basename+".o"
    os.system(comp_cmd)
    return comp_cmd
  def link(self,filename,objs):
    if not os.path.exists(self.dexe):
      os.makedirs(self.dexe)
    basename = os.path.splitext(os.path.basename(filename))[0]
    if self.libs.__len__>0:
      link_cmd = self.cmd_link+" "+"".join([self.dobj+s+" " for s in objs])+"".join([s+" " for s in self.libs])+"-o "+self.dexe+basename
    else:
      link_cmd = self.cmd_link+" "+"".join([self.dobj+s+" " for s in objs])                                    +"-o "+self.dexe+basename
    os.system(link_cmd)
    return link_cmd

class dependency:
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

class parsed_file:
  """
  parsed_file is an object that handles a single parsed file, its attributes and methods.
  """
  def __init__(self,
               name,                     # file name
               program      = False,     # flag for checking if the file is a program
               module       = False,     # flag for checking if the file is a modules file
               include      = False,     # flag for checking if the file is an include-dependency
               to_compile   = False,     # flag for checking if the file must be compiled
               builder      = builder(), # debug builder
               module_names = [],        # in case the file contains modules definition, this is the list of modules defined
               dependencies = [],        # dependency list
               pfile_dep    = []):       # parsed file dependent list
    self.name         = name
    self.program      = program
    self.module       = module
    self.include      = include
    self.to_compile   = to_compile
    self.builder      = builder
    self.module_names = module_names
    self.dependencies = dependencies
    self.pfile_dep    = pfile_dep
    self.basename     = os.path.splitext(os.path.basename(self.name))[0]
    self.timestamp    = os.path.getmtime(self.name)
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
        dep = dependency(dep_type="module",dep_name=matching.group('name'))
        self.dependencies.append(dep)
      matching = re.match(regex_f95_include,line)
      if matching:
        dep = dependency(dep_type="include",dep_name=matching.group('name'))
        self.dependencies.append(dep)
    ffile.close()
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
            # verifying if dep newer than self
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
  def compile(self):
    """
    The method compile compiles current file and all its dependencies if necessary.
    """
    if not self.include:
      if self.to_compile:
        if self.pfile_dep.__len__()>0:
          for dep in self.pfile_dep:
            dep.compile()
        print self.builder.compile(filename=self.name)
        self.to_compile = False
  def build(self):
    """
    The method build builds current file.
    """
    self.compile()
    if self.program:
      objs = self.obj_dependencies()
      print self.builder.link(filename=self.name,objs=objs)

# auxiliary functions definitions
def module_is_in(pfiles,module):
  """
  The function module_is_in find the parsed file containing the desidered module.
  """
  for n,pfile in enumerate(pfiles):
    if pfile.module:
      for module_name in pfile.module_names:
        if module_name==module:
          return pfile.name,n
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
def check_compiling_dependency(pfiles):
  """
  The function check_compiling_dependency refresh the compiling dependency list of the parsed files list.
  """
  for pfile in pfiles:
    pfile.check_compile()
  for pfile in pfiles:
    if any(pf.to_compile for pf in pfile.pfile_dep):
      pfile.to_compile = True

# main parsing loop
if __name__ == '__main__':
  cliargs = cliparser.parse_args()
  if cliargs.which=='clean':
    # cleaning project
    shutil.rmtree(cliargs.dobj)
    shutil.rmtree(cliargs.dmod)
  elif cliargs.which=='build':
    # setting building options
    pfiles = []
    for root, subFolders, files in os.walk(cliargs.src):
      for filename in files:
        if any(os.path.splitext(os.path.basename(filename))[1]==ext for ext in __extensions_parsed__):
          file = os.path.join(root, filename)
          pfile = parsed_file(name=file)
          pfile.builder=builder(compiler=cliargs.compiler,cflags=cliargs.cflags,lflags=cliargs.lflags,libs=cliargs.libs,dobj=cliargs.dobj,dmod=cliargs.dmod,dexe=cliargs.dexe)
          pfile.parse()
          pfiles.append(pfile)
    for pfile in pfiles:
      pfile.pfile_dep = []
      for dep in pfile.dependencies:
        if dep.dep_type=="module":
          dep.dep_file,n = module_is_in(pfiles=pfiles,module=dep.dep_name)
          pfile.pfile_dep.append(pfiles[n])
        if dep.dep_type=="include":
          dep.dep_file,n = include_is_in(pfiles=pfiles,include=dep.dep_name)
          if n>-1:
            pfiles[n].program = False
            pfiles[n].module  = False
            pfiles[n].include = True
            pfile.pfile_dep.append(pfiles[n])
    check_compiling_dependency(pfiles=pfiles)
    # building loop
    for pfile in pfiles:
      if cliargs.target:
        if cliargs.target==pfile.name:
          pfile.build()
      else:
        if pfile.program:
          pfile.build()
          build_file = open("build_"+pfile.basename, "w")
          build_file.writelines(" Building dependency of: "+pfile.name+"\n")
          build_file.writelines("  Dependency list"+"\n")
          for dep in pfile.pfile_dep:
            build_file.writelines("   "+dep.name+"\n")
            build_file.writelines(dep.str_dependencies(pref="     "))
          build_file.close()
