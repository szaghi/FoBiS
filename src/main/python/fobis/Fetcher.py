#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Fetcher.py, module definition of FoBiS.py Fetcher object.

This module handles fetching and building GitHub-hosted FoBiS.py dependencies.
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
  import configparser as configparser
except ImportError:
  import configparser
import os
from .utils import print_fake, syswork


class Fetcher(object):
  """
  Fetcher handles fetching and building GitHub-hosted FoBiS.py dependencies.
  """
  DEPS_CONFIG_FILE = '.deps_config.ini'

  def __init__(self, deps_dir, print_n=None, print_w=None):
    """
    Parameters
    ----------
    deps_dir : str
      directory where dependencies are stored
    print_n : {None}
      function for printing normal messages
    print_w : {None}
      function for printing warning messages
    """
    self.deps_dir = deps_dir
    self.print_n = print_n if print_n is not None else print_fake
    self.print_w = print_w if print_w is not None else print_fake

  def parse_dep_spec(self, spec):
    """
    Parse a dependency spec string into a dict.

    Format: URL [:: branch=X] [:: tag=X] [:: rev=X] [:: mode=X]

    Parameters
    ----------
    spec : str
      dependency specification string

    Returns
    -------
    dict
      parsed fields: 'url', and optionally 'branch', 'tag', 'rev', 'mode'
    """
    parts = [p.strip() for p in spec.split('::')]
    result = {'url': parts[0].strip()}
    for part in parts[1:]:
      if '=' in part:
        key, _, value = part.partition('=')
        result[key.strip()] = value.strip()
    return result

  def fetch(self, name, url, branch=None, tag=None, rev=None, update=False):
    """
    Clone or update a dependency repo.

    Parameters
    ----------
    name : str
      dependency name (used as subdirectory name)
    url : str
      git repository URL
    branch : {None}
      branch to check out
    tag : {None}
      tag to check out
    rev : {None}
      revision/commit to check out
    update : {False}
      if True, run git fetch to update before checking out

    Returns
    -------
    str
      path to the cloned dependency directory
    """
    dep_dir = os.path.join(self.deps_dir, name)
    if not os.path.exists(self.deps_dir):
      os.makedirs(self.deps_dir)
    if not os.path.exists(dep_dir):
      self.print_n('Cloning ' + name + ' from ' + url)
      result = syswork('git clone ' + url + ' ' + dep_dir)
      if result[0] != 0:
        self.print_w('Error cloning ' + name + ':\n' + result[1])
        return dep_dir
    elif update:
      self.print_n('Updating ' + name)
      result = syswork('git -C ' + dep_dir + ' fetch')
      if result[0] != 0:
        self.print_w('Error fetching updates for ' + name + ':\n' + result[1])
    else:
      self.print_n('Dependency ' + name + ' already fetched (use --update to refresh)')
    ref = tag or branch or rev
    if ref:
      self.print_n('Checking out ' + ref + ' for ' + name)
      result = syswork('git -C ' + dep_dir + ' checkout ' + ref)
      if result[0] != 0:
        self.print_w('Error checking out ' + ref + ' for ' + name + ':\n' + result[1])
    return dep_dir

  def build_dep(self, name, dep_dir, mode=None):
    """
    Build a dependency using FoBiS.py build.

    Parameters
    ----------
    name : str
      dependency name (for messages)
    dep_dir : str
      path to the dependency directory
    mode : {None}
      fobos mode to use for building
    """
    fobos_file = os.path.join(dep_dir, 'fobos')
    if not os.path.exists(fobos_file):
      self.print_w('Error: dependency "' + name + '" has no fobos file in ' + dep_dir)
      return
    self.print_n('Building dependency ' + name)
    old_pwd = os.getcwd()
    os.chdir(dep_dir)
    if mode:
      result = syswork('FoBiS.py build -mode ' + mode)
    else:
      result = syswork('FoBiS.py build')
    os.chdir(old_pwd)
    if result[0] != 0:
      self.print_w('Error building ' + name + ':\n' + result[1])
    else:
      self.print_n(result[1])

  def save_config(self, deps_info):
    """
    Write the deps config file with dependon entries for use by FoBiS.py build.

    Parameters
    ----------
    deps_info : list
      list of dicts with keys 'name', 'path', 'mode'
    """
    config = configparser.RawConfigParser()
    config.add_section('deps')
    dependon_entries = []
    for dep in deps_info:
      fobos_path = os.path.join(dep['path'], 'fobos')
      if dep.get('mode'):
        entry = fobos_path + ':' + dep['mode']
      else:
        entry = fobos_path
      dependon_entries.append(entry)
    config.set('deps', 'dependon', ' '.join(dependon_entries))
    config_path = os.path.join(self.deps_dir, self.DEPS_CONFIG_FILE)
    with open(config_path, 'w') as cfg_file:
      config.write(cfg_file)
    self.print_n('Saved deps config to ' + config_path)

  def load_config(self):
    """
    Read the deps config file and return list of dependon strings.

    Returns
    -------
    list
      list of dependon entry strings (e.g. ['.fobis_deps/mylib/fobos:gnu'])
    """
    config_path = os.path.join(self.deps_dir, self.DEPS_CONFIG_FILE)
    if not os.path.exists(config_path):
      return []
    config = configparser.RawConfigParser()
    config.read(config_path)
    if config.has_option('deps', 'dependon'):
      value = config.get('deps', 'dependon')
      return value.split()
    return []
