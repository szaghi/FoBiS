#!/usr/bin/env python
"""Testing FoBiS.py"""
# import doctest
import os
import unittest
from fobis.config import __config__
from fobis.fobis import build
from fobis.fobis import clean
from fobis.fobos import Fobos


class SuiteTest(unittest.TestCase):
  """Testing suite for FoBiS.py."""

  @staticmethod
  def run_build(directory):
    """
    Method for running the build into a selected directory.

    Parameters
    ----------
    directory : str
      relative path to tested directory
    """
    print("Testing " + directory)
    old_pwd = os.getcwd()
    os.chdir(os.path.dirname(os.path.abspath(__file__)) + '/' + directory)
    __config__.get_cli(['clean', '-f', 'fobos'])
    Fobos(filename=__config__.cliargs.fobos)
    clean()
    __config__.get_cli(['build', '-f', 'fobos'])
    Fobos(filename=__config__.cliargs.fobos)
    build()
    build_ok = os.path.exists(directory)
    __config__.get_cli(['rule', '-f', 'fobos', '-ex', 'finalize'])
    fobos = Fobos(filename=__config__.cliargs.fobos)
    fobos.rule_execute(rule=__config__.cliargs.execute)
    __config__.get_cli(['clean', '-f', 'fobos'])
    Fobos(filename=__config__.cliargs.fobos)
    clean()
    os.chdir(old_pwd)
    return build_ok

  def test_buildings(self):
    """Testing buildings."""
    num_failures = 0
    failed = []

    for test in range(5):
      build_ok = self.run_build('test' + str(test + 1))
      if not build_ok:
        failed.append('test' + str(test + 1))
        num_failures += 1

    if len(failed) > 0:
      for fail in failed:
        print(fail)
    self.assertEquals(num_failures, 0)
    return


if __name__ == "__main__":
  unittest.main()
