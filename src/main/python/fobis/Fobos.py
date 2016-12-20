"""
fobos.py, module definition of fobos class.
This is a class aimed at fobos file handling.
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
from __future__ import print_function
try:
  import ConfigParser as configparser
except ImportError:
  import configparser
from copy import deepcopy
import os
import re
import sys
from .utils import check_results, print_fake, syswork


class Fobos(object):
  """
  Fobos is an object that handles fobos file, its attributes and methods.
  """
  def __init__(self, cliargs, print_n=None, print_w=None):
    """
    Parameters
    ----------
    cliargs : argparse object
    print_n : {None}
      function for printing normal message
    print_w : {None}
      function for printing emphized warning message
    """
    if print_n is None:
      self.print_n = print_fake
    else:
      self.print_n = print_n

    if print_w is None:
      self.print_w = print_fake
    else:
      self.print_w = print_w

    self.fobos = None
    self.mode = None
    self.local_variables = {}
    if cliargs.fobos:
      filename = cliargs.fobos
    else:
      filename = 'fobos'
    if os.path.exists(filename):
      self.fobos = configparser.ConfigParser()
      if not cliargs.fobos_case_insensitive:
        self.fobos.optionxform = str  # case sensitive
      self.fobos.read(filename)
      self._set_cliargs(cliargs=cliargs)
    return

  def _check_mode(self, mode):
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
          self.print_w('Error: the mode "' + mode + '" is not defined into the fobos file.')
          self.modes_list()
          sys.exit(1)
      else:
        self.print_w('Error: fobos file has not "modes" section.')
        sys.exit(1)
    return

  def _set_mode(self, mode=None):
    """
    Function for setting the selected mode.

    Parameters
    ----------
    mode : {None}
      selected mode
    """
    if self.fobos:
      if mode:
        self._check_mode(mode=mode)
      else:
        if self.fobos.has_option('modes', 'modes'):
          self.mode = self.fobos.get('modes', 'modes').split()[0]  # first mode selected
        else:
          if self.fobos.has_section('default'):
            self.mode = 'default'
          else:
            self.print_w('Error: fobos file has not "modes" section neither "default" one')
            sys.exit(1)
    return

  def _check_template(self):
    """
    Function for checking the correct use of "template" sections.
    """
    if self.fobos:
      for mode in self.fobos.sections():
        if self.fobos.has_option(mode, 'template'):
          if self.fobos.has_section(self.fobos.get(mode, 'template')):
            for item in self.fobos.items(self.fobos.get(mode, 'template')):
              self.fobos.set(mode, item[0], item[1])
          else:
            self.print_w('Error: mode "' + mode + '" uses as template the mode "' + self.fobos.get(mode, 'template') + '" that is NOT defined')
            sys.exit(1)
    return

  def _get_local_variables(self):
    """
    Get the definition of local variables defined into any sections (modes).
    """
    if self.fobos:
      for section in self.fobos.sections():
        for item in self.fobos.items(section):
          if item[0].startswith('$'):
            self.local_variables[item[0]] = item[1]
    return

  def _substitute_local_variables_mode(self):
    """
    Substitute the definition of local variables defined into the mode (section) selected.
    """
    if self.fobos and self.mode:
      self._substitute_local_variables_section(section=self.mode)
    return

  def _substitute_local_variables_section(self, section):
    """
    Substitute the definition of local variables defined into a section.
    """
    if self.fobos:
      if self.fobos.has_section(section):
        for item in self.fobos.items(section):
          item_val = item[1]
          for key, value in self.local_variables.items():
            item_val = re.sub(re.escape(key), value, item_val)
            # item_val = re.sub(r"(?!" + re.escape(key) + r"[aZ_-])\s*" + re.escape(key) + r"\s*", value, item_val)
          self.fobos.set(section, item[0], item_val)
    return

  def _check_local_variables(self):
    """
    Get and substitute the definition of local variables defined into any sections (modes).
    """
    if self.fobos:
      self._get_local_variables()
      if len(self.local_variables) > 0:
        self._substitute_local_variables_mode()
    return

  def _set_cliargs_attributes(self, cliargs, cliargs_dict):
    """
    Set attributes of cliargs from fobos options.

    Parameters
    ----------
    cliargs : argparse object
    cliargs_dict : argparse object attributes dictionary
    """
    if self.mode:
      for item in self.fobos.items(self.mode):
        if item[0] in cliargs_dict:
          if isinstance(cliargs_dict[item[0]], bool):
            setattr(cliargs, item[0], self.fobos.getboolean(self.mode, item[0]))
          elif isinstance(cliargs_dict[item[0]], int):
            setattr(cliargs, item[0], int(item[1]))
          elif isinstance(cliargs_dict[item[0]], list):
            setattr(cliargs, item[0], item[1].split())
          else:
            setattr(cliargs, item[0], item[1])
    return

  @staticmethod
  def _check_cliargs_cflags(cliargs, cliargs_dict):
    """
    Method for setting attribute of cliargs.

    Parameters
    ----------
    cliargs : argparse object
    cliargs_dict : argparse object attributes dictionary
    """
    for item in cliargs_dict:
      if item in ['cflags', 'lflags', 'preproc']:
        val_cli = cliargs_dict[item]
        val_fobos = getattr(cliargs, item)
        if item == 'cflags':
          if val_cli == '-c':
            match = re.search(r'(-c\s+|-c$)', val_fobos)
            if match:
              val_cli = ''  # avoid multiple -c flags
        if val_fobos and val_cli:
          setattr(cliargs, item, val_fobos + ' ' + val_cli)
    return

  def _set_cliargs(self, cliargs):
    """
    Set cliargs from fobos options.

    Parameters
    ----------
    cliargs : argparse object
    """
    if self.fobos:
      cliargs_dict = deepcopy(cliargs.__dict__)
      if cliargs.which != 'rule':
        self._set_mode(mode=cliargs.mode)
      self._check_template()
      self._check_local_variables()
      self._set_cliargs_attributes(cliargs=cliargs, cliargs_dict=cliargs_dict)
      self._check_cliargs_cflags(cliargs=cliargs, cliargs_dict=cliargs_dict)
    return

  def get(self, option, mode=None, toprint=True):
    """
    Get options defined into the fobos file.

    Parameters
    ----------
    option : str
      option name
    mode : {None}
      eventual mode name
    toprint : {True}
      return of the value: if toprint==False the value is return otherwise is printed to stdout
    """
    value = ''
    if self.fobos:
      self._set_mode(mode=mode)
      if self.fobos.has_option(self.mode, option):
        value = self.fobos.get(self.mode, option)
    if toprint:
      self.print_w(value)
      return
    else:
      return value

  def get_output_name(self, mode=None, toprint=True):
    """
    Method for building the output name accordingly to the fobos options.

    Parameters
    ----------
    mode : {None}
      eventual mode name
    toprint : {True}
      return of the value: if toprint==False the value is return otherwise is printed to stdout
    """
    output = ''
    build_dir = self.get(option='build_dir', mode=mode, toprint=False)
    mklib = self.get(option='mklib', mode=mode, toprint=False)
    if self.fobos:
      self._set_mode(mode=mode)
      if self.fobos.has_option(self.mode, 'output'):
        output = self.fobos.get(self.mode, 'output')
        output = os.path.normpath(os.path.join(build_dir, output))
      elif self.fobos.has_option(self.mode, 'target'):
        output = self.fobos.get(self.mode, 'target')
        output = os.path.splitext(os.path.basename(output))[0]
        if mklib.lower() == 'shared':
          output = output + '.so'
        elif mklib.lower() == 'static':
          output = output + '.a'
        output = os.path.normpath(os.path.join(build_dir, output))
    if toprint:
      self.print_w(output)
      return
    else:
      return output

  def modes_list(self):
    """List defined modes."""
    if self.fobos:
      self.print_n('The fobos file defines the following modes:')
      if self.fobos.has_option('modes', 'modes'):
        modes = self.fobos.get('modes', 'modes').split()
        for mode in modes:
          if self.fobos.has_section(mode):
            if self.fobos.has_option(mode, 'help'):
              helpmsg = self.fobos.get(mode, 'help')
            else:
              helpmsg = ''
            self.print_n('  - "' + mode + '" ' + helpmsg)
      else:
        self.print_w('Error: no modes are defined into the fobos file!')
        sys.exit(1)
    sys.exit(0)
    return

  @staticmethod
  def print_template(cliargs):
    """
    Print fobos template.

    Parameters
    ----------
    cliargs : argparse object
    """
    print("[default]")
    for argument in vars(cliargs):
      attribute = getattr(cliargs, argument)
      if isinstance(attribute, list):
        attribute = ' '.join(attribute)
      print(str(argument) + " = " + str(attribute))

  def rules_list(self, quiet=False):
    """
    Function for listing defined rules.

    Parameters
    ----------
    quiet : {False}
      less verbose outputs than default
    """
    if self.fobos:
      self.print_n('The fobos file defines the following rules:')
      for rule in self.fobos.sections():
        if rule.startswith('rule-'):
          if self.fobos.has_option(rule, 'help'):
            helpmsg = self.fobos.get(rule, 'help')
          else:
            helpmsg = ''
          self.print_n('  - "' + rule.split('rule-')[1] + '" ' + helpmsg)
          if self.fobos.has_option(rule, 'quiet'):
            quiet = self.fobos.getboolean(rule, 'quiet')
          for rul in self.fobos.options(rule):
            if rul.startswith('rule'):
              if not quiet:
                self.print_n('       Command => ' + self.fobos.get(rule, rul))
    sys.exit(0)
    return

  def rule_execute(self, rule, quiet=False, log=False):
    """
    Function for executing selected rule.

    Parameters
    ----------
    rule : str
      rule name
    quiet : {False}
      less verbose outputs than default
    log : {False}
      bool for activate errors log saving
    """
    if self.fobos:
      self.print_n('Executing rule "' + rule + '"')
      rule_name = 'rule-' + rule
      if self.fobos.has_section(rule_name):
        self._get_local_variables()
        self._substitute_local_variables_section(section=rule_name)
        results = []
        quiet = False
        log = False
        if self.fobos.has_option(rule_name, 'quiet'):
          quiet = self.fobos.getboolean(rule_name, 'quiet')
        if self.fobos.has_option(rule_name, 'log'):
          log = self.fobos.getboolean(rule_name, 'log')
        for rul in self.fobos.options(rule_name):
          if rul.startswith('rule'):
            if not quiet:
              self.print_n('   Command => ' + self.fobos.get(rule_name, rul))
            result = syswork(self.fobos.get(rule_name, rul))
            results.append(result)
        if log:
          check_results(results=results, log='rules_errors.log', print_w=self.print_w)
        else:
          check_results(results=results, print_w=self.print_w)
      else:
        self.print_w('Error: the rule "' + rule + '" is not defined into the fobos file. Defined rules are:')
        self.rules_list(quiet=quiet)
        sys.exit(1)
    return
