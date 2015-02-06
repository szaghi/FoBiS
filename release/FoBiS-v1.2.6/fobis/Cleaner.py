#!/usr/bin/env python
"""
Cleaner.py, module definition of Cleaner class.
This is a class designed for controlling the cleaning phase.
"""
import os
import shutil
from .config import __config__


class Cleaner(object):
  """
  Cleaner is an object for cleaning current project.
  """
  def __init__(self,
               build_dir="./",    # directory containing built files
               mod_dir="./",    # directory containing .mod files
               obj_dir="./",    # directory containing compiled object files
               target=None,    # target files
               output=None,    # names of compiled tragets
               mklib=None):   # create library
    self.build_dir = build_dir
    self.mod_dir = build_dir + mod_dir
    self.obj_dir = build_dir + obj_dir
    self.target = target
    self.output = output
    self.mklib = mklib

  def clean_mod(self):
    """
    Function clean_mod clean compiled MODs directory.
    """
    if os.path.exists(self.mod_dir):
      print(__config__.colors.red + 'Removing ' + self.mod_dir + __config__.colors.end)
      shutil.rmtree(self.mod_dir)

  def clean_obj(self):
    """
    Function clean_obj clean compiled OBJs directory.
    """
    if os.path.exists(self.obj_dir):
      print(__config__.colors.red + 'Removing ' + self.obj_dir + __config__.colors.end)
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
          if self.mklib.lower() == 'static':
            exe = os.path.splitext(os.path.basename(self.target))[0] + '.a'
          elif self.mklib.lower() == 'shared':
            exe = os.path.splitext(os.path.basename(self.target))[0] + '.so'
        else:
          exe = os.path.splitext(os.path.basename(self.target))[0]
      if os.path.exists(self.build_dir + exe):
        print(__config__.colors.red + 'Removing ' + self.build_dir + exe + __config__.colors.end)
        os.remove(self.build_dir + exe)
      if os.path.exists('build_' + os.path.splitext(os.path.basename(self.target))[0] + '.log'):
        print(__config__.colors.red + 'Removing build_' + os.path.splitext(os.path.basename(self.target))[0] + '.log' + __config__.colors.end)
        os.remove('build_' + os.path.splitext(os.path.basename(self.target))[0] + '.log')
