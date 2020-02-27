#!/usr/bin/env python
"""Build script for FoBiS.py"""
import os
from pybuilder.core import init, task, use_plugin
from shutil import copyfile
import subprocess
import re

use_plugin('python.core')
use_plugin('python.coverage')
use_plugin('python.flake8')
use_plugin('python.frosted')
use_plugin('python.install_dependencies')
use_plugin('python.pylint')
use_plugin('python.unittest')

__source__ = open('src/main/python/fobis/FoBiSConfig.py').read()
__version__ = re.search(r'^__version__\s*=\s*"(.*)"', __source__, re.M).group(1)
try:
  __branch__ = str(subprocess.check_output(['git', 'symbolic-ref', '--quiet', '--short', 'HEAD'])).strip('\n')
except subprocess.CalledProcessError as e:
  __branch__ = 'unknown'

__branch__ = re.sub(r'feature/', '', __branch__)
__branch__ = re.sub(r'hotfix/', '', __branch__)

@init
def initialize(project):
  """Initiale the building class."""
  project.version = __version__
  project.build_depends_on('coverage')
  project.build_depends_on('flake8')
  project.build_depends_on('frosted')
  project.build_depends_on('pylint')

  project.set_property("teamcity_output", True)

  project.set_property('flake8_max_line_length', 500)
  project.set_property('verbose', True)

  project.set_property('coverage_break_build', False)
  project.set_property('coverage_threshold_warn', 90)

  project.set_property('dir_target', 'release')
  project.set_property('dir_dist', 'release/' + project.name + '-' + __branch__)
  project.set_property('dir_reports', 'release/reports-' + project.name + '-' + __branch__)

  project.default_task = ['analyze', 'publish', 'copy_resources']
  return


@task
def copy_resources(project):
  """Copy non source resource files."""
  copyfile('MANIFEST.in', 'release/' + project.name + '-' + __branch__ + '/MANIFEST.in')
  copyfile('src/main/scripts/setup.py', 'release/' + project.name + '-' + __branch__ + '/setup.py')
  for mdf in os.listdir('.'):
    if mdf.endswith('.md'):
      copyfile(mdf, 'release/' + project.name + '-' + __branch__ + '/' + mdf)
  return
