"""
ParsedFile.py, module definition of Dependency class.
This is a class designed for handling a single parsed file.
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
try:
  import graphviz as gvz
  import functools
  __graph__ = functools.partial(gvz.Graph, format='svg')
  __digraph__ = functools.partial(gvz.Digraph, format='svg')
  __styles__ = {'graph': {'fontsize': '16',
                          'fontcolor': 'black',
                          'bgcolor': 'white',
                          'rankdir': 'BT'},
                'nodes': {'fontname': 'Helvetica',
                          'shape': 'box',
                          'fontcolor': 'black',
                          'color': 'black',
                          'style': 'filled, rounded',
                          'fillcolor': 'white'},
                'edges': {'style': 'dashed',
                          'color': 'black',
                          'arrowhead': 'open',
                          'fontname': 'Courier',
                          'fontsize': '12',
                          'fontcolor': 'black'}}
  __graphviz__ = True

  def add_nodes(graph, nodes):
    """
    Auxiliary function for adding nodes to the dependency graph.

    Parameters
    ----------
    graph : __graph__ object
    nodes : nodes to be added to the graph
    """
    for node in nodes:
      if isinstance(node, tuple):
        graph.node(node[0], **node[1])
      else:
        graph.node(node)
    return graph

  def add_edges(graph, edges):
    """
    Auxiliary function for adding edges to the dependency graph.

    Parameters
    ----------
    graph : __graph__ object
    edges : nodes to be added to the graph
    """
    for edge in edges:
      if isinstance(edge[0], tuple):
        graph.edge(*edge[0], **edge[1])
      else:
        graph.edge(*edge)
    return graph

  def apply_styles(graph):
    """
    Auxiliary function for adding styles to the dependency graph.

    Parameters
    ----------
    graph : __graph__ object
    """
    graph.graph_attr.update(('graph' in __styles__ and __styles__['graph']) or {})
    graph.node_attr.update(('nodes' in __styles__ and __styles__['nodes']) or {})
    graph.edge_attr.update(('edges' in __styles__ and __styles__['edges']) or {})
    return graph
except ImportError:
  __graphviz__ = False
import operator
import os
import re
import sys
from .Dependency import Dependency
from .utils import traverse_recursive
from .utils import unique_seq
# definition of regular expressions
__str_apex__ = r"('|" + r'")'
__str_kw_include__ = r"[Ii][Nn][Cc][Ll][Uu][Dd][Ee]"
__str_kw_intrinsic__ = r"[Ii][Nn][Tt][Rr][Ii][Nn][Ss][Ii][Cc]"
__str_kw_iso_fortran_env__ = r"[Ii][Ss][Oo]_[Ff][Oo][Rr][Tt][Rr][Aa][Nn]_[Ee][Nn][Vv]"
__str_kw_iso_c_binding__ = r"[Ii][Ss][Oo]_[Cc]_[Bb][Ii][Nn][Dd][Ii][Nn][Gg]"
__str_kw_ieee_exceptions__ = r"[Ii][Ee][Ee][Ee]_[Ee][Xx][Cc][Ee][Pp][Tt][Ii][Oo][Nn][Ss]"
__str_kw_ieee_arithmetic__ = r"[Ii][Ee][Ee][Ee]_[Aa][Rr][Ii][Tt][Hh][Mm][Ee][Tt][Ii][Cc]"
__str_kw_ieee_features__ = r"[Ii][Ee][Ee][Ee]_[Ff][Ee][Aa][Tt][Uu][Rr][Ee][Ss]"
__str_kw_module__ = r"[Mm][Oo][Dd][Uu][Ll][Ee]"
__str_kw_program__ = r"[Pp][Rr][Oo][Gg][Rr][Aa][Mm]"
__str_kw_use__ = r"[Uu][Ss][Ee]"
__str_kw_mpifh__ = r"[Mm][Pp][Ii][Ff]\.[Hh]"
__str_name__ = r"(?P<name>[a-zA-Z][a-zA-Z0-9_]*)"
__str_eol__ = r"(?P<eol>\s*!.*|\s*)?$"
# __str_f95_mod_rename__ = r"(\s*,\s*[a-zA-Z][a-zA-Z0-9_]*\s*=>\s*[a-zA-Z][a-zA-Z0-9_]*)*"
# __str_f95_mod_only__ = r"(\s*,\s*[Oo][Nn][Ll][Yy]\s*:\s*([a-zA-Z][a-zA-Z0-9_]*\s*=>\s*[a-zA-Z][a-zA-Z0-9_]*|[a-zA-Z][a-zA-Z0-9_]*))*"
__str_use_mod__ = (r"^(\s*)" +  # eventual initial white spaces
                   __str_kw_use__ +  # keyword "use"
                   r"(\s*,\s*.*\s*::)*" +  # eventual module nature
                   r"(\s+)" +  # 1 or more white spaces
                   __str_name__ +  # construct name
                   r"(?P<mod_eol>(.*))")
__str_use_mod_intrinsic__ = (r"^(\s*)" +  # eventual initial white spaces
                             __str_kw_use__ +  # keyword "use"
                             r"\s*,\s*" + __str_kw_intrinsic__ + r"\s*::.*" +  # keyword intrinsic
                             r"(?P<mod_eol>(.*))")
__str_use_mod_iso_fortran_env__ = (r"^(\s*)" +  # eventual initial white spaces
                                   __str_kw_use__ +  # keyword "use"
                                   r"\s+" + __str_kw_iso_fortran_env__ +  # keyword intrinsic module iso_fortran_env
                                   r"(?P<mod_eol>(.*))")
__str_use_mod_iso_c_binding__ = (r"^(\s*)" +  # eventual initial white spaces
                                 __str_kw_use__ +  # keyword "use"
                                 r"\s+" + __str_kw_iso_c_binding__ +  # keyword intrinsic module iso_c_binding
                                 r"(?P<mod_eol>(.*))")
__str_use_mod_ieee_exceptions__ = (r"^(\s*)" +  # eventual initial white spaces
                                   __str_kw_use__ +  # keyword "use"
                                   r"\s+" + __str_kw_ieee_exceptions__ +  # keyword intrinsic module ieee_exceptions
                                   r"(?P<mod_eol>(.*))")
__str_use_mod_ieee_arithmetic__ = (r"^(\s*)" +  # eventual initial white spaces
                                   __str_kw_use__ +  # keyword "use"
                                   r"\s+" + __str_kw_ieee_arithmetic__ +  # keyword intrinsic module ieee_arithmetic
                                   r"(?P<mod_eol>(.*))")
__str_use_mod_ieee_features__ = (r"^(\s*)" +  # eventual initial white spaces
                                 __str_kw_use__ +  # keyword "use"
                                 r"\s+" + __str_kw_ieee_features__ +  # keyword intrinsic module ieee_features
                                 r"(?P<mod_eol>(.*))")
__str_include__ = (r"^(\s*|\#)" +  # eventual initial white spaces or "#" character
                   __str_kw_include__ +  # keyword "include"
                   r"(\s+)" +  # 1 or more white spaces
                   __str_apex__ +  # character "'" or '"'
                   r"(\s*)" +  # eventaul white spaces
                   r"(?P<name>.*)" +  # name of included file
                   r"(\s*)" +  # eventaul white spaces
                   __str_apex__ +  # character "'" or '"'
                   __str_eol__)  # eventual eol white space and or comment
__str_module__ = (r"^(\s*)" +  # eventual initial white spaces
                  r"(?P<scplevel>" + __str_kw_module__ + r")" +  # keyword "module"
                  r"(\s+)" +  # 1 or more white spaces
                  __str_name__ +  # construct name
                  __str_eol__)  # eventual eol white space and or comment
__str_program__ = (r"^(\s*)" +  # eventual initial white spaces
                   r"(?P<scplevel>" + __str_kw_program__ + r")" +  # keyword "program"
                   r"(\s+)" +  # 1 or more white spaces
                   __str_name__ +  # construct name
                   __str_eol__)  # eventual eol white space and or comment
__str_mpifh__ = (r"(.*)" + __str_kw_mpifh__ + r"(.*)")
__regex_use_mod__ = re.compile(__str_use_mod__)
__regex_include__ = re.compile(__str_include__)
__regex_program__ = re.compile(__str_program__)
__regex_module__ = re.compile(__str_module__)
__regex_use_mod_intrinsic__ = re.compile(__str_use_mod_intrinsic__)
__regex_use_mod_iso_fortran_env__ = re.compile(__str_use_mod_iso_fortran_env__)
__regex_use_mod_iso_c_binding__ = re.compile(__str_use_mod_iso_c_binding__)
__regex_use_mod_ieee_exceptions__ = re.compile(__str_use_mod_ieee_exceptions__)
__regex_use_mod_ieee_arithmetic__ = re.compile(__str_use_mod_ieee_arithmetic__)
__regex_use_mod_ieee_features__ = re.compile(__str_use_mod_ieee_features__)
__regex_use_intrinsic_modules__ = [__regex_use_mod_intrinsic__,
                                   __regex_use_mod_iso_fortran_env__,
                                   __regex_use_mod_iso_c_binding__,
                                   __regex_use_mod_ieee_exceptions__,
                                   __regex_use_mod_ieee_arithmetic__,
                                   __regex_use_mod_ieee_features__]
__regex_mpifh__ = re.compile(__str_mpifh__)


class ParsedFile(object):
  """ParsedFile is an object that handles a single parsed file, its attributes and methods."""
  def __init__(self, name, program=False, module=False, include=False, nomodlib=False, to_compile=False, output=None):
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
    return

  def sort_dependencies(self):
    """
    Method for sorting dependencies.
    """
    for dep in self.pfile_dep_all:
      for other_dep in self.pfile_dep_all:
        if other_dep != dep:
          if dep in other_dep.pfile_dep_all:
            dep.order += 1
    self.pfile_dep_all.sort(key=operator.attrgetter('order'), reverse=True)
    return

  def parse(self, inc):
    """
    The method parse parses the file creating its the dependencies list and the list of modules names that self eventually contains.

    Parameters
    ----------
    inc : list
      list of extensions of included files
    """
    self.module_names = []
    self.dependencies = []
    ffile = open(self.name, "r")
    for line in ffile:
      matching = re.match(__regex_program__, line)
      if matching:
        self.program = True
      matching = re.match(__regex_module__, line)
      if matching:
        self.module = True
        self.module_names.append(matching.group('name'))
      matching = re.match(__regex_use_mod__, line)
      if matching:
        if not any(re.match(regex, line) for regex in __regex_use_intrinsic_modules__):
          if matching.group('name').lower() != 'mpi' and matching.group('name').lower() != 'omp_lib':
            dep = Dependency(dtype="module", name=matching.group('name'))
            self.dependencies.append(dep)
      matching = re.match(__regex_include__, line)
      if matching:
        if not re.match(__regex_mpifh__, line):
          dep = Dependency(dtype="include", name=matching.group('name'))
          self.dependencies.append(dep)
    ffile.close()
    if not self.program and not self.module:
      if os.path.splitext(os.path.basename(self.name))[1] not in inc:
        self.nomodlib = True

  def save_build_log(self, builder):
    """
    The method save_build_log save a log file containing information about the building options used.

    Parameters
    ----------
    builder : Builder object
      builder used for building self
    """
    with open("build_" + self.basename + ".log", "w") as log_file:
      log_file.writelines("Hierarchical dependencies list of: " + self.name + "\n")
      for dep in self.pfile_dep:
        log_file.writelines("  " + dep.name + "\n")
        log_file.writelines(dep.str_dependencies(pref="    "))
      log_file.writelines("Complete ordered dependencies list of: " + self.name + "\n")
      for dep in self.pfile_dep_all:
        log_file.writelines("  " + dep.name + "\n")
      log_file.writelines(builder.verbose())
    return

  def save_dep_graph(self):
    """
    Method for saving dependency graph.
    """
    if __graphviz__:
      depgraph = __digraph__()
      depgraph = add_nodes(depgraph, [self.name])
      depgraph.graph_attr['label'] = 'Dependencies graph of ' + self.name
      for dep in self.pfile_dep:
        depgraph = add_nodes(depgraph, [dep.name])
        depgraph = add_edges(depgraph, [(self.name, dep.name)])
        for subdep in dep.str_dependencies().split("\n"):
          if subdep != '':
            depgraph = add_nodes(depgraph, [subdep])
            depgraph = add_edges(depgraph, [(dep.name, subdep)])
      depgraph = apply_styles(depgraph)
      depgraph.render("dependency_graph_" + self.basename)
    else:
      print("Module 'graphviz' not found: saving of dependency graph disabled")
    return

  def gnu_make_rule(self, builder):
    """
    Method returning the file compiling rule in GNU Make format.

    Parameters
    ----------
    builder : Builder object

    Returns
    -------
    str
      string containing the compiling rule of the file
    """
    string = []
    if not self.include:
      file_dep = [self.name]
      for dep in self.pfile_dep:
        if dep.include:
          file_dep.append(dep.name)
      if (len(self.pfile_dep) - len(file_dep)) >= 0:
        string.append("$(DOBJ)" + self.basename.lower() + ".o:" + "".join([" " + f for f in file_dep]) + " \\" + "\n")
        for dep in self.pfile_dep[:-1]:
          if not dep.include:
            string.append("\t$(DOBJ)" + os.path.splitext(os.path.basename(dep.name))[0].lower() + ".o \\" + "\n")
        if not self.pfile_dep[-1].include:
          string.append("\t$(DOBJ)" + os.path.splitext(os.path.basename(self.pfile_dep[-1].name))[0].lower() + ".o\n")
      else:
        string.append("$(DOBJ)" + self.basename.lower() + ".o:" + "".join([" " + f for f in file_dep]) + "\n")
      string.append("\t@echo $(COTEXT)\n")
      string.append("\t@$(FC) $(OPTSC) " + ''.join(['-I' + i + ' ' for i in builder.dinc]) + " $< -o $@\n")
      string.append("\n")
    return "".join(string)

  def str_dependencies(self,
                       pref=""):  # prefixing string
    """
    The method str_dependencies create a string containing the depencies files list.
    """
    str_dep = ""
    for dep in self.pfile_dep:
      str_dep += pref + dep.name + "\n"
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
