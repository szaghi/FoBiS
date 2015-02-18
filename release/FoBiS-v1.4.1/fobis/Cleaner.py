#!/usr/bin/env python
"""
Cleaner.py, module definition of Cleaner class.
This is a class designed for controlling the cleaning phase.
"""
import os
from .config import __config__


class Cleaner(object):
  """
  Cleaner is an object for cleaning current project.
  """
  def __init__(self,
               build_dir="." + os.sep,
               obj_dir="." + os.sep,
               mod_dir="." + os.sep,
               target=None,
               output=None,
               mklib=None):
    """
    Parameters
    ----------
    build_dir : {"./"}
      directory containing built files
    obj_dir : {"./"}
      directory containing compiled object files
    mod_dir : {"./"}
      directory containing .mod files
    target : {None}
      target source to be built
    output : {None}
      name of the building output
    mklib : {None}
      flag for building a library instead of a program
    """
    self.__sanitize_dirs(build_dir=build_dir, obj_dir=obj_dir, mod_dir=mod_dir)
    self.__sanitize_files(target=target, output=output)
    self.mklib = mklib
    return

  def __sanitize_dirs(self, build_dir, obj_dir, mod_dir):
    """
    Method for sanitizing directory paths.

    Parameters
    ----------
    build_dir : str
      directory containing built files
    obj_dir : str
      directory containing compiled object files
    mod_dir : str
      directory containing .mod files
    """
    self.build_dir = os.path.normpath(build_dir) + os.sep
    self.obj_dir = os.path.normpath(build_dir + obj_dir) + os.sep
    self.mod_dir = os.path.normpath(build_dir + mod_dir) + os.sep
    return

  def __sanitize_files(self, target, output):
    """
    Method for sanitizing files paths.

    Parameters
    target : {None}
      target source to be built
    output : {None}
      name of the building output
    ----------
    """
    if target:
      self.target = os.path.normpath(target)
    else:
      self.target = target
    if output:
      self.output = os.path.normpath(output)
    else:
      self.output = output
    return

  def clean_mod(self):
    """
    Method for cleaning compiled mod files.
    """
    if os.path.exists(self.mod_dir):
      print(__config__.colors.red + 'Removing all *.mod files into "' + self.mod_dir + '"' + __config__.colors.end)
      for root, subfolders, files in os.walk(self.mod_dir):
        for filename in files:
          if os.path.splitext(os.path.basename(filename))[1] == '.mod':
            os.remove(os.path.join(root, filename))

  def clean_obj(self):
    """
    Method for cleaning compiled objects files.
    """
    if os.path.exists(self.obj_dir):
      print(__config__.colors.red + 'Removing all *.o files into "' + self.obj_dir + '"' + __config__.colors.end)
      for root, subfolders, files in os.walk(self.obj_dir):
        for filename in files:
          if os.path.splitext(os.path.basename(filename))[1] == '.o':
            os.remove(os.path.join(root, filename))

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
      if __config__.cliargs.cflags_heritage:
        if os.path.exists('.cflags.heritage'):
          os.remove('.cflags.heritage')
