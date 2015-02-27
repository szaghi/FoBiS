#!/usr/bin/env python
"""
Cleaner.py, module definition of Cleaner class.
This is a class designed for controlling the cleaning phase.
"""
import os
from .utils import print_fake


class Cleaner(object):
  """
  Cleaner is an object for cleaning current project.
  """
  def __init__(self, cliargs, print_w=None):
    """
    Parameters
    ----------
    cliargs : argparse object
    print_w : {None}
      function for printing emphized warning message

    Attributes
    ----------
    build_dir : str
      directory containing built files
    obj_dir : str
      directory containing compiled object files
    mod_dir : str
      directory containing .mod files
    target : str
      target source to be built
    output : str
      name of the building output
    mklib : str
      flag for building a library instead of a program
    print_w : function
      function for printing emphized warning message
    """

    if print_w is None:
      self.print_w = print_fake
    else:
      self.print_w = print_w

    self._sanitize_dirs(build_dir=cliargs.build_dir, obj_dir=cliargs.obj_dir, mod_dir=cliargs.mod_dir)
    self._sanitize_files(target=cliargs.target, output=cliargs.output)
    self.mklib = cliargs.mklib
    return

  def _sanitize_dirs(self, build_dir, obj_dir, mod_dir):
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

  def _sanitize_files(self, target, output):
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
      self.print_w('Removing all *.mod files into "' + self.mod_dir + '"')
      for root, _, files in os.walk(self.mod_dir):
        for filename in files:
          if os.path.splitext(os.path.basename(filename))[1] == '.mod':
            os.remove(os.path.join(root, filename))

  def clean_obj(self):
    """
    Method for cleaning compiled objects files.
    """
    if os.path.exists(self.obj_dir):
      self.print_w('Removing all *.o files into "' + self.obj_dir + '"')
      for root, _, files in os.walk(self.obj_dir):
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
        self.print_w('Removing ' + self.build_dir + exe)
        os.remove(self.build_dir + exe)
      if os.path.exists('build_' + os.path.splitext(os.path.basename(self.target))[0] + '.log'):
        self.print_w('Removing build_' + os.path.splitext(os.path.basename(self.target))[0] + '.log')
        os.remove('build_' + os.path.splitext(os.path.basename(self.target))[0] + '.log')
      if os.path.exists('dependency_graph_' + os.path.splitext(os.path.basename(self.target))[0] + '.svg'):
        self.print_w('Removing dependency_graph_' + os.path.splitext(os.path.basename(self.target))[0] + '.svg')
        os.remove('dependency_graph_' + os.path.splitext(os.path.basename(self.target))[0] + '.svg')
      if os.path.exists('dependency_graph_' + os.path.splitext(os.path.basename(self.target))[0]):
        self.print_w('Removing dependency_graph_' + os.path.splitext(os.path.basename(self.target))[0])
        os.remove('dependency_graph_' + os.path.splitext(os.path.basename(self.target))[0])
      if os.path.exists(self.build_dir + '.cflags.heritage'):
        os.remove(self.build_dir + '.cflags.heritage')
