"""
Dependency.py, module definition of Dependency class.

This is a class designed for handling file dependency.
"""
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals
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
from future import standard_library
standard_library.install_aliases()
from builtins import str
from builtins import *
from builtins import object
import os


class Dependency(object):

  """Dependency is an object that handles a single file dependency, its attributes and methods."""

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
