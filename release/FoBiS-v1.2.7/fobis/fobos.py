#!/usr/bin/env python
"""
fobos.py, module definition of fobos class.
This is a class aimed at fobos file handling.
"""
try:
  import ConfigParser as configparser
except ImportError:
  import configparser
from copy import deepcopy
import os
import re
import sys
from .config import __config__
from .utils import syswork


class Fobos(object):
  """
  Fobos is an object that handles fobos file, its attributes and methods.
  """
  def __init__(self,
               filename='fobos'):
    """
    Parameters
    ----------
    filename : {'fobos'}
      file name of the fobos file
    """
    self.fobos = None
    self.mode = None
    self.local_variables = {}
    if os.path.exists(filename):
      self.fobos = configparser.ConfigParser()
      self.fobos.optionxform = str  # case sensitive
      self.fobos.read(filename)
      # checking if local variables have been defined into fobos
      for section in self.fobos.sections():
        for item in self.fobos.items(section):
          if item[0].startswith('$'):
            self.local_variables[item[0]] = item[1]
      self.__set_cliargs__()
      __config__.update_extensions()
    return

  def __check_mode__(self, mode):
    """
    Function for checking the presence of the selected mode into the set defined inside the fobos.

    Parameters
    ----------
    mode : str
      name of the selcted mode
    """
    if self.fobos:
      if self.fobos.has_option('modes', 'modes'):
        if mode in self.fobos.get('modes', 'modes'):
          self.mode = mode
        else:
          print(__config__.colors.red + 'Error: the mode "' + mode + '" is not defined into the fobos file.' + __config__.colors.end)
          self.modes_list(color=__config__.colors.red)
          sys.exit(1)
      else:
        print(__config__.colors.red + 'Error: fobos file has not "modes" section.' + __config__.colors.end)
        sys.exit(1)
    return

  def __set_mode__(self):
    """
    Function for setting the selected mode.
    """
    if self.fobos:
      if __config__.cliargs.mode:
        self.__check_mode__(mode=__config__.cliargs.mode)
      else:
        if self.fobos.has_option('modes', 'modes'):
          self.mode = self.fobos.get('modes', 'modes').split()[0]  # first mode selected
        else:
          if self.fobos.has_section('default'):
            self.mode = 'default'
          else:
            print(__config__.colors.red + 'Error: fobos file has not "modes" section neither "default" one' + __config__.colors.end)
            sys.exit(1)
    return

  def __check_template__(self):
    """
    Function for checking the correct use of "template" sections.
    """
    if self.fobos:
      if self.mode:
        if self.fobos.has_option(self.mode, 'template'):
          if self.fobos.has_section(self.fobos.get(self.mode, 'template')):
            for item in self.fobos.items(self.fobos.get(self.mode, 'template')):
              self.fobos.set(self.mode, item[0], item[1])
          else:
            print(__config__.colors.red + 'Error: mode "' + self.mode + '" uses as template the mode "' + self.fobos.get(self.mode, 'template') + '" that is NOT defined' + __config__.colors.end)
            sys.exit(1)
    return

  def __set_cliargs__(self):
    """
    Function for setting cliargs from fobos settings.
    """
    if self.fobos:
      cliargs_dict = deepcopy(__config__.cliargs.__dict__)
      self.__set_mode__()
      self.__check_template__()

      for item in self.fobos.items(self.mode):
        if item[0] in cliargs_dict:
          item_value = item[1]
          if len(self.local_variables) > 0:
            # the fobos defines some local variables: parsing the opstions for local variables expansion
            for key, value in self.local_variables.iteritems():
              if key in item_value:
                item_value = item_value.replace(key, value)
          # if type(cliargs_dict[item[0]]) == type(False):
          if isinstance(cliargs_dict[item[0]], bool):
            setattr(__config__.cliargs, item[0], self.fobos.getboolean(self.mode, item[0]))
          # elif type(cliargs_dict[item[0]]) == type(1):
          elif isinstance(cliargs_dict[item[0]], int):
            setattr(__config__.cliargs, item[0], int(item[1]))
          # elif type(cliargs_dict[item[0]]) == type([]):
          elif isinstance(cliargs_dict[item[0]], list):
            setattr(__config__.cliargs, item[0], item[1].split())
          else:
            setattr(__config__.cliargs, item[0], item_value)
      for item in cliargs_dict:
        if item in ['cflags', 'lflags', 'preproc']:
          val_cli = cliargs_dict[item]
          val_fobos = getattr(__config__.cliargs, item)
          if item == 'cflags':
            if val_cli == '-c':
              match = re.search(r'(-c\s+|-c$)', val_fobos)
              if match:
                val_cli = ''  # avoid multiple -c flags
          if val_fobos and val_cli:
            setattr(__config__.cliargs, item, val_fobos + ' ' + val_cli)
      if __config__.cliargs.colors:
        __config__.colors.enable()
      else:
        __config__.colors.disable()
    return

  def modes_list(self, color=__config__.colors.bld):
    """
    Function for listing defined modes.

    Parameters
    ----------
    color : __config__.colors.bld
      printing color
    """
    if self.fobos:
      print(color + 'The fobos file defines the following modes:' + __config__.colors.end)
      if self.fobos.has_option('modes', 'modes'):
        modes = self.fobos.get('modes', 'modes').split()
        for mode in modes:
          if self.fobos.has_section(mode):
            if self.fobos.has_option(mode, 'help'):
              helpmsg = self.fobos.get(mode, 'help')
            else:
              helpmsg = ''
            print(color + '  - "' + mode + '" ' + __config__.colors.end + helpmsg)
      else:
        print(__config__.colors.red + 'Error: no modes are defined into the fobos file!' + __config__.colors.end)
        sys.exit(1)
    sys.exit(0)
    return

  def rules_list(self, color=__config__.colors.bld):
    """
    Function for listing defined rules.

    Parameters
    ----------
    color : __config__.colors.bld
      printing color
    """
    if self.fobos:
      print(color + 'The fobos file defines the following rules:' + __config__.colors.end)
      for rule in self.fobos.sections():
        if rule.startswith('rule-'):
          if self.fobos.has_option(rule, 'help'):
            helpmsg = self.fobos.get(rule, 'help')
          else:
            helpmsg = ''
          print(color + '  - "' + rule.split('rule-')[1] + '" ' + __config__.colors.end + helpmsg)
          if self.fobos.has_option(rule, 'quiet'):
            quiet = self.fobos.getboolean(rule, 'quiet')
          else:
            quiet = __config__.cliargs.quiet
          for rul in self.fobos.options(rule):
            if rul.startswith('rule'):
              if not quiet:
                print(color + '       Command => ' + self.fobos.get(rule, rul) + __config__.colors.end)
    sys.exit(0)
    return

  def rule_execute(self, rule):
    """
    Function for executing selected rule.

    Parameters
    ----------
    rule : str
      rule name
    """
    if self.fobos:
      print(__config__.colors.bld + ' Executing rule "' + rule + '"' + __config__.colors.end)
      rule_name = 'rule-' + rule
      if self.fobos.has_section(rule_name):
        if self.fobos.has_option(rule_name, 'quiet'):
          quiet = self.fobos.getboolean(rule_name, 'quiet')
        else:
          quiet = __config__.cliargs.quiet
        for rul in self.fobos.options(rule_name):
          if rul.startswith('rule'):
            if not quiet:
              print(__config__.colors.bld + '   Command => ' + self.fobos.get(rule_name, rul) + __config__.colors.end)
            result = syswork(self.fobos.get(rule_name, rul))
            if result[0] != 0:
              print(__config__.colors.red + result[1] + __config__.colors.end)
              sys.exit(1)
        sys.exit(0)
      else:
        print(__config__.colors.red + 'Error: the rule "' + rule + '" is not defined into the fobos file. Defined rules are:' + __config__.colors.end)
        self.rules_list(color=__config__.colors.red)
        sys.exit(1)
    return
