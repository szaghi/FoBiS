#!/usr/bin/env python
"""Setup script for install FoBiS.py"""
# import pypandoc
import re
from setuptools import setup
__source__ = open('fobis/FoBiSConfig.py').read()
__license__ = re.search(r'^__license__\s*=\s*"(.*)"', __source__, re.M).group(1)

if __name__ == '__main__':
  setup(name                  = re.search(r'^__appname__\s*=\s*"(.*)"', __source__, re.M).group(1),
        version               = re.search(r'^__version__\s*=\s*"(.*)"', __source__, re.M).group(1),
        description           = re.search(r'^__description__\s*=\s*"(.*)"', __source__, re.M).group(1),
        long_description      = re.search(r'^__long_description__\s*=\s*"(.*)"', __source__, re.M).group(1),
        # long_description      = pypandoc.convert('README.md', 'rst'),
        author                = re.search(r'^__author__\s*=\s*"(.*)"', __source__, re.M).group(1),
        author_email          = re.search(r'^__author_email__\s*=\s*"(.*)"', __source__, re.M).group(1),
        url                   = re.search(r'^__url__\s*=\s*"(.*)"', __source__, re.M).group(1),
        scripts               = ['FoBiS.py'],
        packages              = ['fobis'],
        py_modules            = [],
        classifiers           = ['Development Status :: 5 - Production/Stable',
                                 'License :: OSI Approved :: '+__license__,
                                 'Environment :: Console',
                                 'Intended Audience :: End Users/Desktop',
                                 'Programming Language :: Python',
                                 'Programming Language :: Python :: 2',
                                 'Programming Language :: Python :: 2.7',
                                 'Programming Language :: Python :: 3',
                                 'Programming Language :: Python :: 3.4',
                                 'Topic :: Text Processing'],
        entry_points          = { 'console_scripts': [] },
        extras_require        = { 'PreForM.py':  ["PreForM.py>=v1.1.1"],
                                  'FORD': ["FORD>=1.1.0"],
                                  'graphviz': ["graphviz>=0.4.2"]})
        # install_requires      = [ "multiprocessing" ])
