#!/usr/bin/env python
"""Build script for MaTiSSe.py"""
import os
from pybuilder.core import Author, init, task, use_plugin
from shutil import copyfile
import re

use_plugin('python.core')
use_plugin('python.coverage')
use_plugin('python.flake8')
use_plugin('python.frosted')
use_plugin('python.install_dependencies')
use_plugin('python.pylint')
# use_plugin('python.unittest')

__source__ = open('src/main/python/fobis/config.py').read()

authors = [Author(re.search(r'^__author__\s*=\s*"(.*)"', __source__, re.M).group(1),
                  re.search(r'^__author_email__\s*=\s*"(.*)"', __source__, re.M).group(1))]
version = re.search(r'^__version__\s*=\s*"(.*)"', __source__, re.M).group(1)
license = re.search(r'^__license__\s*=\s*"(.*)"', __source__, re.M).group(1)
description = re.search(r'^__description__\s*=\s*"(.*)"', __source__, re.M).group(1)
url = re.search(r'^__url__\s*=\s*"(.*)"', __source__, re.M).group(1)


@init
def initialize(project):
  """Initializing the building class."""
  project.version = version
  project.build_depends_on('coverage')
  project.build_depends_on('flake8')
  project.build_depends_on('frosted')
  project.build_depends_on('pylint')
  # project.depends_on('yattag')

  project.set_property('flake8_max_line_length', 500)
  project.set_property('verbose', True)

  project.set_property('coverage_break_build', False)
  project.set_property('coverage_threshold_warn', 90)

  project.set_property('dir_target', 'release')
  project.set_property('dir_dist', 'release/' + project.name + '-' + project.version)
  project.set_property('dir_reports', 'release/reports-' + project.name + '-' + project.version)

  project.default_task = ['analyze', 'publish', 'copy_resources']
  return


@task
def copy_resources(project):
  """Copy non source resource files."""
  copyfile('MANIFEST.in', 'release/' + project.name + '-' + project.version + '/MANIFEST.in')
  for mdf in os.listdir('.'):
    if mdf.endswith('.md'):
      copyfile(mdf, 'release/' + project.name + '-' + project.version + '/' + mdf)
  return
