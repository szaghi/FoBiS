import { defineConfig } from 'vitepress'
// Generated with the rule pages by docs/scripts/gen_lint_rules.py
import lintRulesSidebar from '../lint-rules/sidebar.json'

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
      {
        text: 'Guide',
        items: [
          { text: 'About',             link: '/guide/' },
          { text: 'Installation',      link: '/guide/installation' },
          { text: 'Quick Start',       link: '/guide/quickstart' },
          { text: 'Shell Completion',  link: '/guide/shell-completion' },
          { text: 'Compilers',         link: '/guide/compilers' },
          { text: 'Claude Skill',      link: '/guide/claude-skill' },
          { text: 'Changelog',         link: '/guide/changelog' },
          { text: 'Contributing',      link: '/guide/contributing' },
        ],
      },
      { text: 'fobos',     link: '/fobos/' },
      { text: 'Reference', link: '/reference/build' },
      { text: 'Advanced',  link: '/advanced/' },
      {
        text: 'Analysis',
        items: [
          { text: 'Analysis & AI', link: '/ai/' },
          { text: 'Linting',       link: '/ai/lint' },
          { text: 'Lint Rules',    link: '/lint-rules/' },
          { text: 'Knowledge Packs', link: '/ai/knowledge-packs' },
          { text: 'Asking Questions', link: '/ai/ask' },
          { text: 'Explaining Failures', link: '/ai/explain' },
          { text: 'Reviewing a Change', link: '/ai/review' },
          { text: 'Resolving Merge Conflicts', link: '/ai/merge-assist' },
          { text: 'Generating Tests', link: '/ai/testgen' },
          { text: 'MCP Server',    link: '/ai/mcp' },
          { text: 'Local LLM Runtime', link: '/ai/runtime' },
          { text: 'Local Models',  link: '/ai/models' },
        ],
      },
      { text: 'Ecosystem', link: '/advanced/ecosystem' },
      { text: 'Examples',  link: '/examples/' },
      { text: 'GitHub',    link: 'https://github.com/szaghi/FoBiS' },
    ],

    sidebar: {
      '/guide/': [
        {
          text: 'Introduction',
          items: [
            { text: 'About FoBiS.py',    link: '/guide/' },
            { text: 'Installation',      link: '/guide/installation' },
            { text: 'Quick Start',       link: '/guide/quickstart' },
            { text: 'Shell Completion',  link: '/guide/shell-completion' },
          ],
        },
        {
          text: 'Compilers',
          items: [
            { text: 'Supported Compilers', link: '/guide/compilers' },
          ],
        },
        {
          text: 'Tooling',
          items: [
            { text: 'Claude Code Skill', link: '/guide/claude-skill' },
          ],
        },
        {
          text: 'Project',
          items: [
            { text: 'Changelog',    link: '/guide/changelog' },
            { text: 'Contributing', link: '/guide/contributing' },
          ],
        },
      ],

      '/fobos/': [
        {
          text: 'fobos file',
          items: [
            { text: 'Overview',           link: '/fobos/' },
            { text: 'Complete Example',   link: '/fobos/complete-example' },
            { text: 'Single Mode',        link: '/fobos/single-mode' },
            { text: 'Many Modes',         link: '/fobos/many-modes' },
            { text: 'Templates',          link: '/fobos/templates' },
            { text: 'Variables',          link: '/fobos/variables' },
            { text: 'Rules',              link: '/fobos/rules' },
            { text: 'Intrinsic Rules',    link: '/fobos/intrinsic-rules' },
            { text: 'Project Metadata',   link: '/fobos/project' },
          ],
        },
        {
          text: 'Special sections',
          items: [
            { text: 'Feature Flags',       link: '/advanced/features' },
            { text: 'Varsets',             link: '/advanced/varsets' },
            { text: 'Includes',            link: '/advanced/includes' },
            { text: 'Dependencies',        link: '/advanced/fetch' },
            { text: 'Lock File & Semver',  link: '/advanced/lock-file' },
            { text: 'Test Runner',         link: '/advanced/testing' },
            { text: 'Cases',               link: '/advanced/cases' },
            { text: 'Verify',              link: '/advanced/verify' },
            { text: 'Shadow modes & Matrix', link: '/advanced/matrix' },
            { text: 'Assess',              link: '/advanced/assess' },
            { text: 'Diff-run',            link: '/advanced/diff-run' },
            { text: 'Coverage',            link: '/reference/coverage' },
            { text: 'External Libraries',  link: '/advanced/externals' },
            { text: 'Build Profiles',      link: '/advanced/build-profiles' },
            { text: 'Lint',                link: '/fobos/lint' },
          ],
        },
      ],

      '/reference/': [
        {
          text: 'Build & Run',
          items: [
            { text: 'build',      link: '/reference/build' },
            { text: 'run',        link: '/reference/run' },
            { text: 'test',       link: '/reference/test' },
            { text: 'coverage',   link: '/reference/coverage' },
            { text: 'check',      link: '/reference/check' },
            { text: 'case',       link: '/reference/case' },
            { text: 'provenance', link: '/reference/provenance' },
            { text: 'verify',     link: '/reference/verify' },
            { text: 'matrix',     link: '/reference/matrix' },
            { text: 'assess',     link: '/reference/assess' },
            { text: 'diff-run',   link: '/reference/diff-run' },
          ],
        },
        {
          text: 'Project',
          items: [
            { text: 'fetch',      link: '/reference/fetch' },
            { text: 'install',    link: '/reference/install' },
            { text: 'introspect', link: '/reference/introspect' },
            { text: 'tree',       link: '/reference/tree' },
            { text: 'cache',      link: '/reference/cache' },
            { text: 'ecosystem',  link: '/reference/ecosystem' },
          ],
        },
        {
          text: 'Utilities',
          items: [
            { text: 'clean',    link: '/reference/clean' },
            { text: 'rule',     link: '/reference/rule' },
            { text: 'doctests', link: '/reference/doctests' },
            { text: 'scaffold', link: '/reference/scaffold' },
          ],
        },
        {
          text: 'Analysis & AI',
          items: [
            { text: 'lint',     link: '/reference/lint' },
            { text: 'review',   link: '/reference/review' },
            { text: 'merge-assist', link: '/reference/merge-assist' },
            { text: 'testgen',  link: '/reference/testgen' },
            { text: 'kb',       link: '/reference/kb' },
            { text: 'ask',      link: '/ai/ask#options' },
            { text: 'mcp',      link: '/ai/mcp' },
            { text: 'llm',      link: '/reference/llm' },
            { text: 'commit',   link: '/reference/commit' },
          ],
        },
      ],

      '/ai/': [
        {
          text: 'Analysis & AI',
          items: [
            { text: 'Overview',          link: '/ai/' },
            { text: 'Linting',           link: '/ai/lint' },
            { text: 'Lint Rules',        link: '/lint-rules/' },
            { text: 'Knowledge Packs',   link: '/ai/knowledge-packs' },
            { text: 'Asking Questions',  link: '/ai/ask' },
            { text: 'Explaining Failures', link: '/ai/explain' },
            { text: 'Reviewing a Change', link: '/ai/review' },
            { text: 'Resolving Merge Conflicts', link: '/ai/merge-assist' },
            { text: 'Generating Tests',  link: '/ai/testgen' },
            { text: 'MCP Server',        link: '/ai/mcp' },
            { text: 'Local LLM Runtime', link: '/ai/runtime' },
            { text: 'Local Models',      link: '/ai/models' },
            { text: 'LLM Commit Messages', link: '/advanced/commit' },
          ],
        },
        {
          text: 'Reference',
          items: [
            { text: 'lint command',      link: '/reference/lint' },
            { text: 'kb command',        link: '/reference/kb' },
            { text: 'llm command',       link: '/reference/llm' },
            { text: '[lint] section',    link: '/fobos/lint' },
          ],
        },
      ],

      '/lint-rules/': lintRulesSidebar,

      '/advanced/': [
        {
          text: 'Advanced Topics',
          items: [
            { text: 'Overview',                link: '/advanced/' },
          ],
        },
        {
          text: 'Build',
          items: [
            { text: 'Build Profiles',          link: '/advanced/build-profiles' },
            { text: 'Feature Flags',           link: '/advanced/features' },
            { text: 'Varsets',                 link: '/advanced/varsets' },
            { text: 'Includes',                link: '/advanced/includes' },
            { text: 'Build Cache',             link: '/advanced/cache' },
            { text: 'Auto-discovery',          link: '/advanced/auto-discovery' },
            { text: 'External Libraries',      link: '/advanced/externals' },
            { text: 'Parallel Compiling',      link: '/advanced/parallel' },
            { text: 'Volatile Libraries',      link: '/advanced/volatile-libs' },
            { text: 'Flag Heritage',           link: '/advanced/cflags-heritage' },
          ],
        },
        {
          text: 'Testing & Quality',
          items: [
            { text: 'Test Runner',             link: '/advanced/testing' },
            { text: 'Cases & Provenance',      link: '/advanced/cases' },
            { text: 'Verifying Results',       link: '/advanced/verify' },
            { text: 'Shadow Modes & Matrix',   link: '/advanced/matrix' },
            { text: 'Assessing Numerical Error', link: '/advanced/assess' },
            { text: 'Differential Execution',  link: '/advanced/diff-run' },
            { text: 'Doctests',                link: '/advanced/doctests' },
            { text: 'PreForM Preprocessing',   link: '/advanced/preform' },
          ],
        },
        {
          text: 'Dependencies',
          items: [
            { text: 'Fetch Dependencies',      link: '/advanced/fetch' },
            { text: 'Lock File & Semver',      link: '/advanced/lock-file' },
            { text: 'Interdependent Projects', link: '/advanced/interdependent' },
            { text: 'GitHub Install',          link: '/advanced/install' },
          ],
        },
        {
          text: 'Multi-project',
          items: [
            { text: 'Ecosystem',               link: '/advanced/ecosystem' },
          ],
        },
        {
          text: 'Integration',
          items: [
            { text: 'Scaffold Boilerplate',    link: '/advanced/scaffold' },
            { text: 'LLM Commit Messages',     link: '/advanced/commit' },
            { text: 'JSON Output',             link: '/advanced/json-output' },
            { text: 'GNU Makefile',            link: '/advanced/makefile' },
            { text: 'Architecture',            link: '/advanced/architecture' },
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
