#!/usr/bin/env python
"""
Dependency.py, module definition of Dependency class.
This is a class designed for handling file dependency.
"""
import os


class Dependency(object):
  """
  Dependency is an object that handles a single file dependency, its attributes and methods.
  """
  def __init__(self, dtype="", name="", dfile=""):
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

  def __str__(self):
    string = []
    string.append('\n  Type: ' + str(self.type))
    string.append('\n  Name: ' + str(self.name))
    string.append('\n  File: ' + str(self.file))
    return ''.join(string)

  def printf(self):
    """Method for printing dependency data."""
    print(self)
    return

  def exist(self):
    """Method for checking the existance of a dependency file."""
    return os.path.exists(self.file)
