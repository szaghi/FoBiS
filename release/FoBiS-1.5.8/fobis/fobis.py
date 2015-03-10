#!/usr/bin/env python
"""
FoBiS.py, Fortran Building System for poor men
"""
# modules loading
import sys
from .config import __config__


def main():
  """
  Main function.
  """
  __config__.run_fobis()
  sys.exit(0)

if __name__ == '__main__':
  main()
