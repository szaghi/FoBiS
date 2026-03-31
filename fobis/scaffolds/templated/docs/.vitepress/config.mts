import { defineConfig } from 'vitepress'

export default defineConfig({
  title: '{{NAME}}',
  description: '{{SUMMARY}}',
  base: '/{{REPOSITORY_NAME}}/',
  themeConfig: {
    nav: [
      { text: 'Home', link: '/' },
      { text: 'Guide', link: '/guide/' },
      { text: 'GitHub', link: '{{REPOSITORY}}' },
    ],

    sidebar: {
      '/guide/': [
        {
          text: 'Introduction',
          items: [
            { text: 'About', link: '/guide/' },
            { text: 'Installation', link: '/guide/installation' },
            { text: 'Quick Start', link: '/guide/quickstart' },
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
})
