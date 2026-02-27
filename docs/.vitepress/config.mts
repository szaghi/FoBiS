import { defineConfig } from 'vitepress'

export default defineConfig({
  title: 'FoBiS.py',
  description: 'Fortran Building System for poor people — automatic dependency-resolving build tool for modern Fortran projects',
  base: '/FoBiS/',
  markdown: {
    math: true,
    languageAlias: {
      fortran: 'fortran-free-form',
      f90:     'fortran-free-form',
      f95:     'fortran-free-form',
      f03:     'fortran-free-form',
      f08:     'fortran-free-form',
      f77:     'fortran-fixed-form',
    },
  },
  themeConfig: {
    nav: [
      { text: 'Home', link: '/' },
      {
        text: 'Guide',
        items: [
          { text: 'About',        link: '/guide/' },
          { text: 'Installation', link: '/guide/installation' },
          { text: 'Quick Start',  link: '/guide/quickstart' },
          { text: 'Compilers',    link: '/guide/compilers' },
          { text: 'Changelog',    link: '/guide/changelog' },
        ],
      },
      { text: 'fobos',     link: '/fobos/' },
      { text: 'Reference', link: '/reference/build' },
      { text: 'Advanced',  link: '/advanced/' },
      { text: 'Examples',  link: '/examples/' },
      { text: 'GitHub',    link: 'https://github.com/szaghi/FoBiS' },
    ],

    sidebar: {
      '/guide/': [
        {
          text: 'Introduction',
          items: [
            { text: 'About FoBiS.py', link: '/guide/' },
            { text: 'Installation',   link: '/guide/installation' },
            { text: 'Quick Start',    link: '/guide/quickstart' },
          ],
        },
        {
          text: 'Compilers',
          items: [
            { text: 'Supported Compilers', link: '/guide/compilers' },
          ],
        },
        {
          text: 'Project',
          items: [
            { text: 'Changelog', link: '/guide/changelog' },
          ],
        },
      ],

      '/fobos/': [
        {
          text: 'fobos file',
          items: [
            { text: 'Overview',        link: '/fobos/' },
            { text: 'Single Mode',     link: '/fobos/single-mode' },
            { text: 'Many Modes',      link: '/fobos/many-modes' },
            { text: 'Templates',       link: '/fobos/templates' },
            { text: 'Variables',       link: '/fobos/variables' },
            { text: 'Rules',           link: '/fobos/rules' },
            { text: 'Intrinsic Rules', link: '/fobos/intrinsic-rules' },
          ],
        },
      ],

      '/reference/': [
        {
          text: 'Commands',
          items: [
            { text: 'build',    link: '/reference/build' },
            { text: 'clean',    link: '/reference/clean' },
            { text: 'rule',     link: '/reference/rule' },
            { text: 'doctests', link: '/reference/doctests' },
            { text: 'fetch',    link: '/reference/fetch' },
            { text: 'install',  link: '/reference/install' },
          ],
        },
      ],

      '/advanced/': [
        {
          text: 'Advanced Topics',
          items: [
            { text: 'Overview',                link: '/advanced/' },
            { text: 'Parallel Compiling',      link: '/advanced/parallel' },
            { text: 'External Libraries',      link: '/advanced/libraries' },
            { text: 'Interdependent Projects', link: '/advanced/interdependent' },
            { text: 'Volatile Libraries',      link: '/advanced/volatile-libs' },
            { text: 'Flag Heritage',           link: '/advanced/cflags-heritage' },
            { text: 'PreForM Preprocessing',   link: '/advanced/preform' },
            { text: 'Doctests',                link: '/advanced/doctests' },
            { text: 'GNU Makefile',            link: '/advanced/makefile' },
            { text: 'Fetch Dependencies',      link: '/advanced/fetch' },
            { text: 'GitHub Install',           link: '/advanced/install' },
          ],
        },
      ],

      '/examples/': [
        {
          text: 'Examples',
          items: [
            { text: 'Overview',       link: '/examples/' },
            { text: 'Basic Build',    link: '/examples/basic' },
            { text: 'Library',        link: '/examples/library' },
            { text: 'Interdependent', link: '/examples/interdependent' },
            { text: 'PreForM',        link: '/examples/preform' },
          ],
        },
      ],
    },

    socialLinks: [
      { icon: 'github', link: 'https://github.com/szaghi/FoBiS' },
    ],

    search: {
      provider: 'local',
    },

    footer: {
      message: 'Released under the <a href="http://www.gnu.org/licenses/gpl-3.0.html">GPL v3 License</a>.',
      copyright: 'Copyright © Stefano Zaghi',
    },
  },
})
