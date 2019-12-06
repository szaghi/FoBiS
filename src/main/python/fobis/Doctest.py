"""
Doctest.py, module definition of Doctest class.

This is a class designed for performing introspective tests
by means of special docstrings.
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
from __future__ import absolute_import
from __future__ import division
from __future__ import unicode_literals
from future import standard_library
standard_library.install_aliases()
from builtins import str
from builtins import *
from builtins import object
import os
import re
__remodule__ = re.compile(r"^(\s*)" +  # eventual initial white spaces
                          r"([Mm][Oo][Dd][Uu][Ll][Ee])" +  # keyword "module"
                          r"(\s+)" +  # 1 or more white spaces
                          r"(?P<name>[a-zA-Z][a-zA-Z0-9_]*)" +  # module name
                          r"(?P<eol>\s*!.*|\s*)?$")  # eventual eol white space and or comment
__redoctest__ = re.compile(r"(?P<doctest>\!.```fortran(?P<test>.*?)\!.```.*?\!\=\>(?P<result>.*?)\<\<\<)", re.DOTALL)


class Doctest(object):
  """Doctest is an object that handles introspective doc-tests for Fortran procedures,
  like the Python doctest module does for Python codes.

  The syntax of a FoBiS.py doctest for Fortran procedures is:
  !$```fortran
  !$ ! valid fortran code for testing the procedure
  !$ ! the doctest must end with printing the expected result to the standard output
  !$```
  !=> !expected results <<<

  Note that the character "$" can be any character, likely it should be the "docmark" you
  select for producing the API documentation by means of the great FORD autodocumentation
  Fortran tool.
  """

  def __init__(self):
    """
    Parameters
    ----------
    """
    self.to_test = False
    self.tests = []

  def parse(self, source):
    """Parse source string for doctest occurences.

    Parameters
    ----------
    source : str
      source string with eventual doctests
    """
    modules = []
    for line in source.split('\n'):
      match = re.match(__remodule__, line)
      if match:
        modules.append(match)
    if len(modules) > 0:
      for match in re.finditer(__redoctest__, source):
        lines = match.group('test').split('\n')
        lines = [line.strip()[2:] for line in lines if not line.strip() == '']
        module_name = None
        for module in modules:
          if module.start() < match.start():
            module_name = module.group('name')
        self.tests.append({'module': module_name, 'source': lines, 'result': match.group('result').strip()})

  def make_volatile_programs(self):
    """Make a 'volatile' program test for each of the parsed doctests."""
    if len(self.tests) > 0:
      self.to_test = True
      for test in self.tests:
        program_source = ["program volatile_doctest"]
        program_source.append("use " + test['module'])
        for line in test['source']:
          program_source.append(line)
        program_source.append("endprogram volatile_doctest")
        test['program_source'] = '\n'.join(program_source)

  def save_volatile_programs(self, build_dir):
    """Save a 'volatile' program test for each of the parsed doctests.

    Parameters
    ----------
    build_dir : str
      build directory where volatile programs are placed

    Returns
    -------
    doctest_root_dir : str
      directory where doctests are saved
    """
    if len(self.tests) > 0:
      doctest_root_dir = os.path.join(build_dir, 'doctests-src')
      for t, test in enumerate(self.tests):
        doctest_dir = os.path.join(doctest_root_dir, test['module'])
        if not os.path.exists(doctest_dir):
          os.makedirs(doctest_dir)
        doctest_file = os.path.join(doctest_dir, test['module'] + '-doctest-' + str(t + 1) + '.f90')
        with open(doctest_file, 'w') as doc:
          doc.writelines(test['program_source'])
        doctest_file = os.path.join(doctest_dir, test['module'] + '-doctest-' + str(t + 1) + '.result')
        with open(doctest_file, 'w') as doc:
          doc.writelines(test['result'])
      return doctest_root_dir
