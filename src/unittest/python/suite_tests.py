#!/usr/bin/env python
"""Testing FoBiS.py"""
# import doctest
import filecmp
import os
import subprocess
import unittest
from fobis.fobis import run_fobis


try:
  subprocess.call(["caf -v"])
  opencoarrays = True
except OSError as e:
  opencoarrays = False

class SuiteTest(unittest.TestCase):
  """Testing suite for FoBiS.py."""

  @staticmethod
  def run_build(directory):
    """
    Method for running the build function into a selected directory.

    Parameters
    ----------
    directory : str
      relative path to tested directory
    """
    print("Testing " + directory)
    build_ok = False
    old_pwd = os.getcwd()
    os.chdir(os.path.dirname(os.path.abspath(__file__)) + '/' + directory)

    run_fobis(fake_args=['clean', '-f', 'fobos'])

    try:
      run_fobis(fake_args=['build', '-f', 'fobos'])
      build_ok = os.path.exists(directory)
    except:
      if directory == 'build-test6':
        with open('building-errors.log') as logerror:
          build_ok = 'Unclassifiable statement' in list(logerror)[-1]
        os.remove('building-errors.log')

    run_fobis(fake_args=['rule', '-f', 'fobos', '-ex', 'finalize'])

    run_fobis(fake_args=['clean', '-f', 'fobos'])

    os.chdir(old_pwd)
    return build_ok

  @staticmethod
  def run_clean(directory):
    """
    Method for running the clean function into a selected directory.

    Parameters
    ----------
    directory : str
      relative path to tested directory
    """
    print("Testing " + directory)
    old_pwd = os.getcwd()
    os.chdir(os.path.dirname(os.path.abspath(__file__)) + '/' + directory)

    run_fobis(fake_args=['build', '-f', 'fobos'])

    run_fobis(fake_args=['clean', '-f', 'fobos'])

    clean_ok = not os.path.exists(directory)
    os.chdir(old_pwd)
    return clean_ok

  @staticmethod
  def make_makefile(directory):
    """
    Make makefile into a selected directory.

    Parameters
    ----------
    directory : str
      relative path to tested directory
    """
    print("Testing " + directory)
    make_ok = False
    old_pwd = os.getcwd()
    os.chdir(os.path.dirname(os.path.abspath(__file__)) + '/' + directory)
    run_fobis(fake_args=['build', '-f', 'fobos', '-m', 'makefile_check'])
    make_ok = filecmp.cmp('makefile_check', 'makefile_ok')
    if not make_ok:
      if os.path.exists('makefile_ok2'):
        make_ok = filecmp.cmp('makefile_check', 'makefile_ok2')
      if not make_ok:
        print('makefile generated')
        with open('makefile_check', 'r') as mk_check:
          print(mk_check.read())
    run_fobis(fake_args=['clean', '-f', 'fobos'])
    os.chdir(old_pwd)
    return make_ok

  @staticmethod
  def run_doctest(directory):
    """
    Method for running the doctest function into a selected directory.

    Parameters
    ----------
    directory : str
      relative path to tested directory
    """
    print("Testing " + directory)
    doctest_ok = True
    old_pwd = os.getcwd()
    os.chdir(os.path.dirname(os.path.abspath(__file__)) + '/' + directory)

    run_fobis(fake_args=['clean', '-f', 'fobos'])

    run_fobis(fake_args=['doctests', '-f', 'fobos'])

    run_fobis(fake_args=['rule', '-f', 'fobos', '-ex', 'finalize'])

    run_fobis(fake_args=['clean', '-f', 'fobos'])

    os.chdir(old_pwd)
    return doctest_ok

  def test_buildings(self):
    """Test buildings."""
    num_failures = 0
    failed = []

    for test in range(20):
      if test + 1 == 15 and not opencoarrays:
        continue
      build_ok = self.run_build('build-test' + str(test + 1))
      if not build_ok:
        failed.append('build-test' + str(test + 1))
        num_failures += 1

    if len(failed) > 0:
      for fail in failed:
        print(fail)
    self.assertEquals(num_failures, 0)
    return

  def test_cleanings(self):
    """Test cleanings."""
    num_failures = 0
    failed = []

    for test in range(1):
      clean_ok = self.run_clean('clean-test' + str(test + 1))
      if not clean_ok:
        failed.append('clean-test' + str(test + 1))
        num_failures += 1

    if len(failed) > 0:
      for fail in failed:
        print(fail)
    self.assertEquals(num_failures, 0)
    return

  def test_makefile(self):
    """Test makefile generation."""
    num_failures = 0
    failed = []

    for test in range(2):
      make_ok = self.make_makefile('makefile-test' + str(test + 1))
      if not make_ok:
        failed.append('makefile-test' + str(test + 1))
        num_failures += 1

    if len(failed) > 0:
      for fail in failed:
        print("Error: Test " + fail + " failed!")
    self.assertEquals(num_failures, 0)
    return

  def test_doctests(self):
    """Test doctests."""
    num_failures = 0
    failed = []

    for test in range(2):
      build_ok = self.run_doctest('doctest-test' + str(test + 1))
      if not build_ok:
        failed.append('doctest-test' + str(test + 1))
        num_failures += 1

    if len(failed) > 0:
      for fail in failed:
        print(fail)
    self.assertEquals(num_failures, 0)
    return


if __name__ == "__main__":
  unittest.main()
