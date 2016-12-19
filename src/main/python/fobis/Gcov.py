"""
Gcov.py, module definition of Gcov class.

This is a class designed for analyzing gcov files.
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
  from pygooglechart import PieChart2D
  __graph__ = True
except ImportError:
  print("Module 'pygooglechart' not found: Gcov graphs disabled")
  __graph__ = False
import os
import re
import sys
from operator import itemgetter
__str_kw_elemental__ = r"[Ee][Ll][Ee][Mm][Ee][Nn][Tt][Aa][Ll]"
__str_kw_pure__ = r"[Pp][Uu][Rr][Ee]"
__str_kw_subroutine__ = r"[Ss][Uu][Bb][Rr][Oo][Uu][Tt][Ii][Nn][Ee]"
__str_kw_function__ = r"[Ff][Uu][Nn][Cc][Tt][Ii][Oo][Nn]"
__str_name__ = r"(?P<name>[a-zA-Z][a-zA-Z0-9_]*)"
__str_procedure__ = (r"^(\s*)" +  # initial white spaces
                     r"(" + __str_kw_elemental__ + r"|" + __str_kw_pure__ + r")?\s+" +  # "elemental" or "pure" attribute
                     r"(?P<ptype>" + __str_kw_function__ + r"|" + __str_kw_subroutine__ + r")\s+" +  # type of procedure
                     r"(?P<pname>" + __str_name__ + r"\s*).*")  # name of procedure
__regex_procedure__ = re.compile(__str_procedure__)


class Gcov(object):
  """Gcov is an object that handles gcov file, its attributes and methods."""

  def __init__(self, filename=None):
    """
    Parameters
    ----------
    filename : {None}
      string containing the gcov filename
    """
    self.filename = filename
    self.procedures = []
    self.coverage = []
    self.metrics = {'coverage': None, 'procedures': None}
    self.l_pie_url = ''
    self.p_pie_url = ''
    return

  def _metrics(self):
    """
    Getg gcov metrics.
    """
    if len(self.coverage) > 0:
      lnumber = sum(1 for cov in self.coverage if isinstance(cov, int))
      elnumber = sum(cov > 0 for cov in self.coverage if isinstance(cov, int))
      unelnumber = sum(cov == 0 for cov in self.coverage if isinstance(cov, int))
      if lnumber > 0:
        elnumber_per = int(round(elnumber * 100. / lnumber))
        unelnumber_per = int(round(unelnumber * 100. / lnumber))
      else:
        elnumber_per = 0
        unelnumber_per = 0
      if elnumber > 0:
        ahits = sum(cov for cov in self.coverage if isinstance(cov, int)) / elnumber
      else:
        ahits = 0
      self.metrics['coverage'] = [str(lnumber), str(elnumber), str(unelnumber), str(elnumber_per), str(unelnumber_per), str(ahits)]
    if len(self.procedures) > 0:
      pnumber = len(self.procedures)
      epnumber = sum(proc[2] > 0 for proc in self.procedures)
      unepnumber = sum(proc[2] == 0 for proc in self.procedures)
      if pnumber > 0:
        epnumber_per = int(round(epnumber * 100. / pnumber))
        unepnumber_per = int(round(unepnumber * 100. / pnumber))
      else:
        epnumber_per = 0
        unepnumber_per = 0
      if epnumber > 0:
        ahits = sum(proc[2] for proc in self.procedures) / epnumber
      else:
        ahits = 0
      self.metrics['procedures'] = [str(pnumber), str(epnumber), str(unepnumber), str(epnumber_per), str(unepnumber_per), str(ahits)]
    return

  def _get_graphs_url(self):
    """
    Get pie-chart graphs urls from online google chart service.

    Returns
    ----------
    str, str
      string containing the url of online google pie-chart graphs
    """
    def pie(size, title, labels, legend, data, colors):
      """
      Function for creating a pie chart.

      Parameters
      ----------
      size : list
        width and height
      title : str
        title of the graph
      lables : list
        list of string containing labels of the data
      legend : list
        list of string containing legend of the data
      data : list
        data to be plotted
      colors : list
        list of string containing the colors of each data in PRGB format

      Returns
      -------
      PieChart2D object
      """
      graph = PieChart2D(size[0], size[1])
      graph.set_title(title)
      graph.set_legend(legend)
      graph.set_pie_labels(labels)
      graph.add_data(data)
      graph.set_colours(colors)
      return graph

    if __graph__:
      if self.metrics['coverage']:
        l_pie = pie(size=[300, 150],
                    title='Coverage of executable lines',
                    labels=[self.metrics['coverage'][3] + '%', self.metrics['coverage'][4] + '%'],
                    legend=['Executed', 'Unexecuted'],
                    data=[int(self.metrics['coverage'][3]), int(self.metrics['coverage'][4])],
                    colors=['65C1FF', 'FF9260'])
        self.l_pie_url = '[![lines](' + l_pie.get_url() + ')]()'
      if self.metrics['procedures']:
        p_pie = pie(size=[300, 150],
                    title='Coverage of procedures',
                    labels=[self.metrics['procedures'][3] + '%', self.metrics['procedures'][4] + '%'],
                    legend=['Executed', 'Unexecuted'],
                    data=[int(self.metrics['procedures'][3]), int(self.metrics['procedures'][4])],
                    colors=['65C1FF', 'FF9260'])
        self.p_pie_url = '[![procedures](' + p_pie.get_url() + ')]()'
    return

  def parse(self):
    """
    Parse gcov file.
    """
    def _coverage_update(ignoring, cov_num, line_num, text, coverage):
      """
      Update coverage list.
      """
      if re.search(r'\bLCOV_EXCL_START\b', text):
        if ignoring:
          sys.stderr.write("Warning: %s:%d: nested LCOV_EXCL_START, "
                           "please fix\n" % (self.filename, line_num))
        ignoring = True
      elif re.search(r'\bLCOV_EXCL_END\b', text):
        if not ignoring:
          sys.stderr.write("Warning: %s:%d: LCOV_EXCL_END outside of "
                           "exclusion zone, please fix\n" % (self.filename,
                                                             line_num))
        ignoring = False
      if cov_num == '-':
        coverage.append(None)
      elif cov_num == '#####':
        if (
            ignoring or
            text.lstrip().startswith(('inline', 'static')) or
            text.strip() == '}' or
            re.search(r'\bLCOV_EXCL_LINE\b', text)
        ):
          coverage.append(None)
        else:
          coverage.append(0)
      elif cov_num == '=====':
        coverage.append(0)
      else:
        coverage.append(int(cov_num))
      return ignoring

    ignoring = False
    if self.filename:
      if os.path.exists(self.filename):
        with open(self.filename, 'r') as source:
          for line in source:
            report_fields = line.split(':')
            cov_num = report_fields[0].strip()
            line_num = int(report_fields[1].strip())
            text = report_fields[2]
            proc_matching = re.match(__regex_procedure__, text)
            if line_num == 0:
              continue
            if proc_matching:
              ptype = proc_matching.group('ptype').strip()
              pname = proc_matching.group('pname').strip()
              if cov_num != '#####' and cov_num != '-':
                pcov = int(cov_num)
              else:
                pcov = 0
              if cov_num != '-':  # needed due to abstract iterfaces
                self.procedures.append([ptype, pname, pcov, line_num])
            ignoring = _coverage_update(ignoring=ignoring, cov_num=cov_num, line_num=line_num, text=text, coverage=self.coverage)
    self._metrics()
    self._get_graphs_url()
    return

  def save(self, report_format='markdown', output=None, graphs=False):
    """
    Save gcov report analysis.

    Parameters
    ----------
    report_format : {'markdown'}
      output format of saved report
    output : {None}
      string output file name
    graphs : {False}
      flag for including graphs
    """
    string = []
    if len(self.metrics) > 0:
      if report_format == 'markdown':
        string.append('### Coverage analysis of *' + os.path.splitext(os.path.basename(self.filename))[0] + '*\n')
        string.append('\n')
        if self.metrics['coverage'] or self.metrics['procedures']:
          string.append('|Metrics|||\n')
          string.append('| --- | --- | --- |\n')
        if self.metrics['coverage']:
          string.append('|Number of executable lines          |' + self.metrics['coverage'][0] + '||\n')
          string.append('|Number of executed lines            |' + self.metrics['coverage'][1] + '|' + self.metrics['coverage'][3] + '%|\n')
          string.append('|Number of unexecuted lines          |' + self.metrics['coverage'][2] + '|' + self.metrics['coverage'][4] + '%|\n')
          string.append('|Average hits per executed line      |' + self.metrics['coverage'][5] + '||\n')
        if self.metrics['procedures']:
          string.append('|Number of procedures                |' + self.metrics['procedures'][0] + '||\n')
          string.append('|Number of executed procedures       |' + self.metrics['procedures'][1] + '|' + self.metrics['procedures'][3] + '%|\n')
          string.append('|Number of unexecuted procedures     |' + self.metrics['procedures'][2] + '|' + self.metrics['procedures'][4] + '%|\n')
          string.append('|Average hits per executed procedure |' + self.metrics['procedures'][5] + '||\n')
        if graphs and __graph__ and (self.metrics['coverage'] or self.metrics['procedures']):
          string.append('\n --- \n')
          if self.metrics['coverage']:
            string.append(self.l_pie_url + '\n')
          if self.metrics['procedures']:
            string.append(self.p_pie_url + '\n')
        string.append('\n#### Unexecuted procedures\n')
        string.append('\n')
        if any(proc[2] == 0 for proc in self.procedures):
          for proc in sorted(self.procedures, key=itemgetter(0, 1)):
            if proc[2] == 0:
              string.append(' + *' + proc[0] + '* **' + proc[1] + '**, line ' + str(proc[3]) + '\n')
        else:
          string.append(' + *none*\n')
        string.append('\n#### Executed procedures\n')
        string.append('\n')
        if any(proc[2] > 0 for proc in self.procedures):
          for proc in sorted(self.procedures, key=itemgetter(2), reverse=True):
            if proc[2] > 0:
              string.append(' + *' + proc[0] + '* **' + proc[1] + '**: tested **' + str(proc[2]) + '** times\n')
        else:
          string.append(' + *none*\n')
        string.append('\n --- \n Report generated by [FoBiS.py](https://github.com/szaghi/FoBiS)')
    if output:
      fout = output
    else:
      fout = os.path.splitext(os.path.basename(self.filename))[0] + '.gcov-report.md'
    with open(fout, 'w') as out:
      out.writelines(string)
    return
