#!/usr/bin/env python
"""
Colors.py, module definition of Colors class.
This is a class aimed at coloring prints.
"""


class Colors(object):
  """
  Colors is an object that handles colors of shell prints, its attributes and methods.
  """
  def __init__(self,
               red='\033[1;31m',
               bld='\033[1m'):
    self.red = red
    self.bld = bld
    self.end = '\033[0m'

  def enable(self):
    """Method for enabling colors."""
    self.red = '\033[1;31m'
    self.bld = '\033[1m'
    self.end = '\033[0m'

  def disable(self):
    """Method for disabling colors."""
    self.red = ''
    self.bld = ''
    self.end = ''
