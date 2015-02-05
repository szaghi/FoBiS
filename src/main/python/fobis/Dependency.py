#!/usr/bin/env python
"""
Dependency.py, module definition of Dependency class.
This is a class designed for handling file dependency.
"""
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
