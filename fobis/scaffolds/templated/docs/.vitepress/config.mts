import { withMermaid } from 'vitepress-plugin-mermaid'

export default withMermaid({
  title: '{{NAME}}',
  description: '{{SUMMARY}}',
  base: '/{{REPOSITORY_NAME}}/',

  markdown: {
    math: true,
    languages: ['fortran-free-form', 'fortran-fixed-form'],
    languageAlias: {
      fortran: 'fortran-free-form',
      f90: 'fortran-free-form',
      f03: 'fortran-free-form',
      f08: 'fortran-free-form',
    },
  },

  themeConfig: {
    nav: [
      { text: 'Home',   link: '/' },
      { text: 'Guide',  link: '/guide/' },
      { text: 'GitHub', link: '{{REPOSITORY}}' },
    ],

    // Add your guide pages here.
    sidebar: {
      '/guide/': [
        {
          text: 'Introduction',
          items: [
            { text: 'About',        link: '/guide/' },
            { text: 'Installation', link: '/guide/installation' },
            { text: 'Quick Start',  link: '/guide/quickstart' },
          ],
        },
        {
          text: 'Project',
          items: [
            { text: 'Contributing', link: '/guide/contributing' },
            { text: 'Changelog',    link: '/guide/changelog' },
          ],
        },
      ],
    },

    socialLinks: [
      { icon: 'github', link: '{{REPOSITORY}}' },
    ],

    search: {
      provider: 'local',
    },

    footer: {
      message: 'Released under the <a href="http://www.gnu.org/licenses/gpl-3.0.html">GPL v3 License</a>.',
      copyright: 'Copyright © {{YEAR}} {{AUTHORS}}',
    },
  },

  mermaid: {},

  vite: {
    // Build with an explicit modern JS target so the docs compile regardless of
    // which mermaid/vitepress/esbuild versions npm resolves. Vite's default
    // es2020 target forces esbuild to down-level modern syntax (e.g. the
    // destructuring mermaid 11.16+ emits), which it refuses to do and the build
    // dies. es2022 needs no lowering and is within VitePress's browser floor.
    build: {
      target: 'es2022',
    },
  },
})
