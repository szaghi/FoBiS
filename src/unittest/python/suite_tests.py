#!/usr/bin/env python
"""Testing columns environment"""
# import doctest
import os
import unittest
import subprocess


def syswork(cmd):
  """
  Function for executing system command 'cmd'.

  Paramters
  ---------
  cmd : str
    command to be extecuted
  """
  error = 0
  try:
    output = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT)
  except subprocess.CalledProcessError as err:
    error = err.returncode
    output = err.output
  return [error, output]


class SuiteTest(unittest.TestCase):
  """Testing suite for FoBiS.py."""

  def test_buildings(self):
    """Testing buildings."""
    num_failures = 0
    failed = []
    err, out = syswork('../../main/python/FoBiS.py clean -f test1/fobos')
    err, out = syswork('../../main/python/FoBiS.py build -f test1/fobos')
    build_ok = os.path.exists('build/Cumbersome')
    if not build_ok:
      failed.append(['test1', err, out])
      num_failures += 1
    if len(failed) > 0:
      for fail in failed:
        print(fail[0])
        print(fail[1])
        print(fail[2])
    self.assertEquals(num_failures, 0)
    return


if __name__ == "__main__":
  unittest.main()
