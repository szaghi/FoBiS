import { defineConfig } from 'vitepress'
// Generated with the rule pages by docs/scripts/gen_lint_rules.py
import lintRulesSidebar from '../lint-rules/sidebar.json'

// One sidebar, in reading order, for every page but the lint rules: prev/next links walk the documentation.
const docs = [
  {
    text: 'Get started',
    items: [
      { text: 'About',            link: '/guide/' },
      { text: 'Installation',     link: '/guide/installation' },
      { text: 'Shell Completion', link: '/guide/shell-completion' },
      { text: 'Compilers',        link: '/guide/compilers' },
    ],
  },
  {
    text: 'Tutorials',
    items: [
      { text: 'Overview', link: '/tutorial/' },
      {
        text: '1. First steps',
        collapsed: false,
        items: [
          { text: '1. A first build',  link: '/tutorial/first-steps/01-first-build' },
          { text: '2. A fobos file',   link: '/tutorial/first-steps/02-fobos' },
          { text: '3. A library',      link: '/tutorial/first-steps/03-library' },
          { text: '4. Tests',          link: '/tutorial/first-steps/04-tests' },
          { text: '5. Dependencies',   link: '/tutorial/first-steps/05-dependencies' },
        ],
      },
      {
        text: '2. Growing a project',
        collapsed: false,
        items: [
          { text: '1. Templates and variables',  link: '/tutorial/growing/01-templates' },
          { text: '2. Profiles and features',    link: '/tutorial/growing/02-profiles' },
          { text: '3. OpenMP and MPI',           link: '/tutorial/growing/03-parallel' },
          { text: '4. A project using quad',     link: '/tutorial/growing/04-dependon' },
          { text: '5. Rules',                    link: '/tutorial/growing/05-rules' },
          { text: '6. Continuous integration',   link: '/tutorial/growing/06-ci' },
          { text: '7. Other build systems',      link: '/tutorial/growing/07-export' },
          { text: '8. quad as a package',        link: '/tutorial/growing/08-packages' },
          { text: '9. One fobos, many machines', link: '/tutorial/growing/09-machines' },
          { text: '10. Programs and a library', link: '/tutorial/growing/10-targets' },
        ],
      },
      {
        text: '3. Many repositories',
        collapsed: false,
        items: [
          { text: '1. An ecosystem',             link: '/tutorial/ecosystem/01-register' },
          { text: '2. The dashboard',            link: '/tutorial/ecosystem/02-dashboard' },
          { text: '3. Acting on every project',  link: '/tutorial/ecosystem/03-exec' },
          { text: '4. Before releasing',         link: '/tutorial/ecosystem/04-check' },
          { text: '5. Shared boilerplate',       link: '/tutorial/ecosystem/05-scaffold' },
          { text: '6. The release train',        link: '/tutorial/ecosystem/06-release' },
        ],
      },
      {
        text: '4. Code quality',
        collapsed: false,
        items: [
          { text: '1. The linter',               link: '/tutorial/quality/01-lint' },
          { text: '2. Suppressions and fixes',   link: '/tutorial/quality/02-fixes' },
          { text: '3. Reviewing a change',       link: '/tutorial/quality/03-review' },
          { text: '4. Querying the code',        link: '/tutorial/quality/04-query' },
          { text: '5. Verified modernisation',   link: '/tutorial/quality/05-modernize' },
          { text: '6. C and Python bindings',    link: '/tutorial/quality/06-bindings' },
          { text: '7. Instructions for agents',  link: '/tutorial/quality/07-agents' },
        ],
      },
      {
        text: '5. Verified numerics',
        collapsed: false,
        items: [
          { text: '1. Cases and quantities',     link: '/tutorial/numerics/01-cases' },
          { text: '2. References',               link: '/tutorial/numerics/02-verify' },
          { text: '3. Defects some builds see',  link: '/tutorial/numerics/03-shadows' },
          { text: '4. How accurate is it?',      link: '/tutorial/numerics/04-assess' },
          { text: '5. Is a refactoring harmless?', link: '/tutorial/numerics/05-diff-run' },
          { text: '6. Is it faster?',            link: '/tutorial/numerics/06-bench' },
          { text: '7. One command for all',      link: '/tutorial/numerics/07-gate' },
          { text: '8. Where the time goes',      link: '/tutorial/numerics/08-profile' },
          { text: '9. On a cluster',             link: '/tutorial/numerics/09-cluster' },
        ],
      },
      {
        text: '6. AI-assisted development',
        collapsed: false,
        items: [
          { text: '1. A local model',            link: '/tutorial/ai/01-model' },
          { text: '2. Build failures, explained', link: '/tutorial/ai/02-explain' },
          { text: '3. Crashes, located',         link: '/tutorial/ai/03-crash' },
          { text: '4. Questions about the code', link: '/tutorial/ai/04-ask' },
          { text: '5. Generated tests',          link: '/tutorial/ai/05-testgen' },
          { text: '6. A second reader',          link: '/tutorial/ai/06-review' },
          { text: '7. Commit messages',          link: '/tutorial/ai/07-commit' },
          { text: '8. Merge conflicts',          link: '/tutorial/ai/08-merge' },
          { text: '9. An agent under the gate',  link: '/tutorial/ai/09-agent' },
        ],
      },
      {
        text: '7. Packages and indexes',
        collapsed: false,
        items: [
          { text: '1. An index of your own',     link: '/tutorial/packages/01-index' },
          { text: '2. Find, add and remove',     link: '/tutorial/packages/02-add' },
          { text: '3. Versions',                 link: '/tutorial/packages/03-versions' },
          { text: '4. Install for your compiler', link: '/tutorial/packages/04-install' },
          { text: '5. Trust without a server',   link: '/tutorial/packages/05-trust' },
        ],
      },
    ],
  },
  {
    text: 'Cookbook',
    items: [
      { text: 'All recipes',                       link: '/cookbook/' },
      { text: 'Building',                          link: '/cookbook/build' },
      { text: 'Libraries and other build systems', link: '/cookbook/libraries' },
      { text: 'Dependencies',                      link: '/cookbook/dependencies' },
      { text: 'Packages and indexes',              link: '/cookbook/packages' },
      { text: 'Testing',                           link: '/cookbook/testing' },
      { text: 'Verifying results',                 link: '/cookbook/verification' },
      { text: 'Code quality',                      link: '/cookbook/analysis' },
      { text: 'AI assistance',                     link: '/cookbook/ai' },
      { text: 'Models, knowledge and agents',      link: '/cookbook/ai-setup' },
      { text: 'Many projects',                     link: '/cookbook/ecosystem' },
      { text: 'CI and machine output',             link: '/cookbook/ci' },
      { text: 'HPC and clusters',                  link: '/cookbook/hpc' },
    ],
  },
  {
    text: 'Reference',
    items: [
      {
        text: 'Commands',
        collapsed: true,
        items: [
          { text: 'All commands', link: '/reference/' },
          { text: 'build',        link: '/reference/build' },
          { text: 'clean',        link: '/reference/clean' },
          { text: 'run',          link: '/reference/run' },
          { text: 'test',         link: '/reference/test' },
          { text: 'doctests',     link: '/reference/doctests' },
          { text: 'coverage',     link: '/reference/coverage' },
          { text: 'install',      link: '/reference/install' },
          { text: 'fetch',        link: '/reference/fetch' },
          { text: 'index',        link: '/reference/index-command' },
          { text: 'search',       link: '/reference/search' },
          { text: 'info',         link: '/reference/info' },
          { text: 'add',          link: '/reference/add' },
          { text: 'remove',       link: '/reference/remove' },
          { text: 'publish',      link: '/reference/publish' },
          { text: 'pkg',          link: '/reference/pkg' },
          { text: 'audit',        link: '/reference/audit' },
          { text: 'tree',         link: '/reference/tree' },
          { text: 'check',        link: '/reference/check' },
          { text: 'introspect',   link: '/reference/introspect' },
          { text: 'rule',         link: '/reference/rule' },
          { text: 'new',          link: '/reference/new' },
          { text: 'scaffold',     link: '/reference/scaffold' },
          { text: 'ecosystem',    link: '/reference/ecosystem' },
          { text: 'fpm',          link: '/reference/fpm' },
          { text: 'case',         link: '/reference/case' },
          { text: 'provenance',   link: '/reference/provenance' },
          { text: 'verify',       link: '/reference/verify' },
          { text: 'matrix',       link: '/reference/matrix' },
          { text: 'assess',       link: '/reference/assess' },
          { text: 'diff-run',     link: '/reference/diff-run' },
          { text: 'bench',        link: '/reference/bench' },
          { text: 'gate',         link: '/reference/gate' },
          { text: 'profile',      link: '/reference/profile' },
          { text: 'lint',         link: '/reference/lint' },
          { text: 'review',       link: '/reference/review' },
          { text: 'query',        link: '/reference/query' },
          { text: 'modernize',    link: '/reference/modernize' },
          { text: 'bindings',     link: '/reference/bindings' },
          { text: 'agents-md',    link: '/reference/agents-md' },
          { text: 'kb',           link: '/reference/kb' },
          { text: 'ask',          link: '/reference/ask' },
          { text: 'merge-assist', link: '/reference/merge-assist' },
          { text: 'testgen',      link: '/reference/testgen' },
          { text: 'commit',       link: '/reference/commit' },
          { text: 'llm',          link: '/reference/llm' },
          { text: 'mcp',          link: '/reference/mcp' },
        ],
      },
      { text: 'fobos Keys',         link: '/fobos/' },
      { text: 'Index Format',       link: '/reference/index-format' },
      { text: 'User Configuration', link: '/reference/configuration' },
      { text: 'Lint Rules',         link: '/lint-rules/' },
      { text: 'Changelog',          link: '/guide/changelog' },
      { text: 'Contributing',       link: '/guide/contributing' },
      { text: 'Architecture',       link: '/advanced/architecture' },
    ],
  },
]

export default defineConfig({
  title: 'FoBiS.py',
  description: 'Fortran Building System — automatic dependency-resolving build tool for modern Fortran projects',
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
    // ```mermaid blocks are left to the browser: .vitepress/theme renders them (and re-renders on dark mode)
    config: (md) => {
      const fence = md.renderer.rules.fence!
      md.renderer.rules.fence = (tokens, idx, options, env, self) => {
        const token = tokens[idx]
        if (token.info.trim() === 'mermaid') {
          return `<pre class="mermaid">${md.utils.escapeHtml(token.content)}</pre>`
        }
        return fence(tokens, idx, options, env, self)
      }
    },
  },
  // A moved page leaves a stub whose front matter says `redirect: /new/path`: the browser is sent on, and search
  // engines are told where the page lives now (tests/test_doc_links.py checks every target exists)
  transformPageData(pageData, { siteConfig }) {
    const target = pageData.frontmatter.redirect
    if (!target) return
    const url = siteConfig.site.base.replace(/\/$/, '') + target
    pageData.frontmatter.head = [
      ...(pageData.frontmatter.head ?? []),
      ['meta', { 'http-equiv': 'refresh', content: `0; url=${url}` }],
      ['link', { rel: 'canonical', href: url }],
    ]
  },
  vite: {
    // An explicit modern target: Vite's default (es2020) makes esbuild down-level the syntax mermaid 11.16+
    // ships, which it refuses to do, and the build dies (same setting as StringiFor and PENF).
    build: {
      target: 'es2022',
    },
  },
  themeConfig: {
    nav: [
      { text: 'Home', link: '/' },
      { text: 'Get started', link: '/guide/', activeMatch: '^/guide/(index|installation|shell-completion|compilers)?$' },
      { text: 'Tutorials', link: '/tutorial/', activeMatch: '^/tutorial/' },
      { text: 'Cookbook', link: '/cookbook/', activeMatch: '^/cookbook/' },
      { text: 'Reference', link: '/reference/', activeMatch: '^/(reference|fobos|lint-rules)/|^/guide/(changelog|contributing)|^/advanced/architecture' },
    ],

    sidebar: {
      '/lint-rules/': lintRulesSidebar,
      '/': docs,
    },

    outline: [2, 3],

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
