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
import shutil
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
    Write the deps config file for use by FoBiS.py build.

    Deps with use='fobos' are written as 'dependon' entries (library approach).
    Deps with use='sources' (default) are written as 'src' entries (direct source inclusion).

    Parameters
    ----------
    deps_info : list
      list of dicts with keys 'name', 'path', 'mode', 'use'
    """
    config = configparser.RawConfigParser()
    config.add_section('deps')
    dependon_entries = []
    src_entries = []
    for dep in deps_info:
      if dep.get('use', 'sources') == 'fobos':
        fobos_path = os.path.join(dep['path'], 'fobos')
        entry = fobos_path + ':' + dep['mode'] if dep.get('mode') else fobos_path
        dependon_entries.append(entry)
      else:
        src_entries.append(dep['path'])
    if dependon_entries:
      config.set('deps', 'dependon', ' '.join(dependon_entries))
    if src_entries:
      config.set('deps', 'src', ' '.join(src_entries))
    config_path = os.path.join(self.deps_dir, self.DEPS_CONFIG_FILE)
    with open(config_path, 'w') as cfg_file:
      config.write(cfg_file)
    self.print_n('Saved deps config to ' + config_path)

  def _resolve_url(self, repo):
    """
    Convert a shorthand repo reference to a full GitHub HTTPS URL.

    Accepts 'user/repo' (GitHub shorthand) or any full URL unchanged.

    Parameters
    ----------
    repo : str
      repository reference

    Returns
    -------
    str
      full git-cloneable URL
    """
    if repo.startswith('http://') or repo.startswith('https://') or repo.startswith('git@'):
      return repo
    return 'https://github.com/' + repo

  def install_from_github(self, repo, branch=None, tag=None, rev=None, mode=None,
                          update=False, no_build=False,
                          prefix='./', bin_dir='bin/', lib_dir='lib/', include_dir='include/'):
    """
    Clone, build, and install a GitHub-hosted FoBiS project.

    Parameters
    ----------
    repo : str
      repository reference ('user/repo' shorthand or full URL)
    branch : {None}
      branch to check out
    tag : {None}
      tag to check out
    rev : {None}
      revision/commit to check out
    mode : {None}
      fobos mode to use when building
    update : {False}
      re-fetch before building
    no_build : {False}
      clone only, skip building and installing
    prefix : str
      installation prefix directory
    bin_dir : str
      sub-directory under prefix for executables
    lib_dir : str
      sub-directory under prefix for libraries
    include_dir : str
      sub-directory under prefix for module files
    """
    url = self._resolve_url(repo)
    name = url.rstrip('/').split('/')[-1]
    if name.endswith('.git'):
      name = name[:-4]
    dep_dir = self.fetch(name, url, branch=branch, tag=tag, rev=rev, update=update)
    if no_build:
      self.print_n('Cloned ' + name + ' to ' + dep_dir + ' (--no-build: skipping build and install)')
      return
    self._build_dep_tracked(name, dep_dir, mode=mode)
    self._install_artifacts(dep_dir, prefix, bin_dir, lib_dir, include_dir)

  def _build_dep_tracked(self, name, dep_dir, mode=None):
    """
    Build a dependency using 'fobis build --track_build'.

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
      self.print_w('Error: "' + name + '" has no fobos file in ' + dep_dir)
      return
    self.print_n('Building ' + name + ' (with --track_build)')
    old_pwd = os.getcwd()
    os.chdir(dep_dir)
    cmd = 'fobis build --track_build'
    if mode:
      cmd += ' -mode ' + mode
    result = syswork(cmd)
    os.chdir(old_pwd)
    if result[0] != 0:
      self.print_w('Error building ' + name + ':\n' + result[1])
    else:
      self.print_n(result[1])

  def _install_artifacts(self, dep_dir, prefix, bin_dir, lib_dir, include_dir):
    """
    Scan dep_dir for .track_build files and copy artifacts to the prefix.

    Parameters
    ----------
    dep_dir : str
      root of the cloned dependency
    prefix : str
      installation prefix
    bin_dir : str
      sub-directory under prefix for executables
    lib_dir : str
      sub-directory under prefix for libraries
    include_dir : str
      sub-directory under prefix for module/include files
    """
    installed_any = False
    for root, _, files in os.walk(dep_dir):
      for filename in files:
        if not filename.endswith('.track_build'):
          continue
        track_file = configparser.ConfigParser()
        track_file.read(os.path.join(root, filename))
        if not track_file.has_option('build', 'output'):
          continue
        output = track_file.get('build', 'output')
        if not os.path.exists(output):
          continue
        is_program = (track_file.has_option('build', 'program') and
                      track_file.get('build', 'program'))
        is_library = (track_file.has_option('build', 'library') and
                      track_file.get('build', 'library'))
        if is_program:
          dest = os.path.join(prefix, bin_dir)
          os.makedirs(dest, exist_ok=True)
          self.print_n('Installing "' + output + '" -> "' + dest + '"')
          shutil.copy(output, dest)
          installed_any = True
        if is_library:
          dest = os.path.join(prefix, lib_dir)
          os.makedirs(dest, exist_ok=True)
          self.print_n('Installing "' + output + '" -> "' + dest + '"')
          shutil.copy(output, dest)
          installed_any = True
          if track_file.has_option('build', 'mod_file'):
            mod_file = track_file.get('build', 'mod_file')
            inc_dest = os.path.join(prefix, include_dir)
            os.makedirs(inc_dest, exist_ok=True)
            self.print_n('Installing "' + mod_file + '" -> "' + inc_dest + '"')
            shutil.copy(mod_file, inc_dest)
    if not installed_any:
      self.print_w('No installable artifacts found. Ensure the project fobos uses --track_build or check the fobos mode.')

  def load_config(self):
    """
    Read the deps config file and return a dict with 'dependon' and 'src' lists.

    Returns
    -------
    dict
      'dependon' : list of fobos-path strings for use=fobos deps
      'src'      : list of directory paths for use=sources deps
      either key is absent when no entries of that type exist
    """
    config_path = os.path.join(self.deps_dir, self.DEPS_CONFIG_FILE)
    if not os.path.exists(config_path):
      return {}
    config = configparser.RawConfigParser()
    config.read(config_path)
    result = {}
    if config.has_option('deps', 'dependon'):
      result['dependon'] = config.get('deps', 'dependon').split()
    if config.has_option('deps', 'src'):
      result['src'] = config.get('deps', 'src').split()
    return result
