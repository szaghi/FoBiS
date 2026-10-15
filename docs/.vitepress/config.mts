import { defineConfig } from 'vitepress'
// Generated with the rule pages by docs/scripts/gen_lint_rules.py
import lintRulesSidebar from '../lint-rules/sidebar.json'

// One sidebar, in reading order, for every page but the lint rules: prev/next links walk the documentation.
const docs = [
  {
    text: 'Start here',
    items: [
      { text: 'About',            link: '/guide/' },
      { text: 'Installation',     link: '/guide/installation' },
      { text: 'Shell Completion', link: '/guide/shell-completion' },
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
    ],
  },
  {
    text: 'Cookbook',
    collapsed: false,
    items: [
      { text: 'All recipes',             link: '/cookbook/' },
      { text: 'Building',                link: '/cookbook/build' },
      { text: 'Dependencies',            link: '/cookbook/dependencies' },
      { text: 'Testing',                 link: '/cookbook/testing' },
      { text: 'Verifying results',       link: '/cookbook/verification' },
      { text: 'Code analysis',           link: '/cookbook/analysis' },
      { text: 'AI assistance',           link: '/cookbook/ai' },
      { text: 'Continuous integration',  link: '/cookbook/ci' },
      { text: 'HPC and clusters',        link: '/cookbook/hpc' },
    ],
  },
  {
    text: 'Guides',
    items: [
      { text: 'All guides', link: '/guide/topics' },
      {
        text: 'Building',
        collapsed: true,
        items: [
          { text: 'Build Profiles',          link: '/advanced/build-profiles' },
          { text: 'Feature Flags',           link: '/advanced/features' },
          { text: 'Varsets',                 link: '/advanced/varsets' },
          { text: 'Includes',                link: '/advanced/includes' },
          { text: 'External Libraries',      link: '/advanced/externals' },
          { text: 'Libraries by Path',       link: '/advanced/libraries' },
          { text: 'Interdependent Projects', link: '/advanced/interdependent' },
          { text: 'Volatile Libraries',      link: '/advanced/volatile-libs' },
          { text: 'Flag Heritage',           link: '/advanced/cflags-heritage' },
          { text: 'Parallel Compiling',      link: '/advanced/parallel' },
          { text: 'Build Cache',             link: '/advanced/cache' },
          { text: 'Source Discovery',        link: '/advanced/auto-discovery' },
          { text: 'Mixed-Language Projects', link: '/advanced/mixed-language' },
          { text: 'PreForM',                 link: '/advanced/preform' },
          { text: 'GNU Makefile Export',     link: '/advanced/makefile' },
          { text: 'fpm',                     link: '/advanced/fpm' },
        ],
      },
      {
        text: 'Dependencies',
        collapsed: true,
        items: [
          { text: 'Fetching Dependencies',   link: '/advanced/fetch' },
          { text: 'Lock File & Semver',      link: '/advanced/lock-file' },
          { text: 'Installing from GitHub',  link: '/advanced/install' },
        ],
      },
      {
        text: 'Testing & Verification',
        collapsed: true,
        items: [
          { text: 'Test Runner',             link: '/advanced/testing' },
          { text: 'Doctests',                link: '/advanced/doctests' },
          { text: 'Cases & Provenance',      link: '/advanced/cases' },
          { text: 'Verifying Results',       link: '/advanced/verify' },
          { text: 'Shadow Modes & Matrix',   link: '/advanced/matrix' },
          { text: 'Assessing Numerical Error', link: '/advanced/assess' },
          { text: 'Differential Runs',       link: '/advanced/diff-run' },
          { text: 'Benchmarks',              link: '/advanced/bench' },
          { text: 'The Gate',                link: '/advanced/gate' },
          { text: 'Clusters',                link: '/advanced/scheduler' },
          { text: 'Profiling',               link: '/advanced/profile' },
        ],
      },
      {
        text: 'Code Quality',
        collapsed: true,
        items: [
          { text: 'Linting',                 link: '/ai/lint' },
          { text: 'Reviewing a Change',      link: '/ai/review' },
          { text: 'Querying the Code',       link: '/advanced/query' },
          { text: 'Verified Modernisation',  link: '/advanced/modernize' },
          { text: 'C and Python Bindings',   link: '/advanced/bindings' },
        ],
      },
      {
        text: 'AI-assisted Development',
        collapsed: true,
        items: [
          { text: 'Overview',                link: '/ai/' },
          { text: 'Knowledge Packs',         link: '/ai/knowledge-packs' },
          { text: 'Asking Questions',        link: '/ai/ask' },
          { text: 'Explaining Failures',     link: '/ai/explain' },
          { text: 'Merge Conflicts',         link: '/ai/merge-assist' },
          { text: 'Generating Tests',        link: '/ai/testgen' },
          { text: 'Commit Messages',         link: '/advanced/commit' },
          { text: 'Local Runtime',           link: '/ai/runtime' },
          { text: 'Local Models',            link: '/ai/models' },
          { text: 'MCP Server',              link: '/ai/mcp' },
          { text: 'Instructions for Agents', link: '/advanced/agents-md' },
          { text: 'Claude Code Skill',       link: '/guide/claude-skill' },
        ],
      },
      {
        text: 'Many Projects',
        collapsed: true,
        items: [
          { text: 'Ecosystem',               link: '/advanced/ecosystem' },
          { text: 'Scaffold',                link: '/advanced/scaffold' },
          { text: 'JSON Output',             link: '/advanced/json-output' },
        ],
      },
    ],
  },
  {
    text: 'Concepts',
    items: [
      { text: 'How a build works',      link: '/concepts/build' },
      { text: 'The verification model', link: '/concepts/verification' },
      { text: 'The AI design',          link: '/concepts/ai' },
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
          { text: 'tree',         link: '/reference/tree' },
          { text: 'check',        link: '/reference/check' },
          { text: 'introspect',   link: '/reference/introspect' },
          { text: 'rule',         link: '/reference/rule' },
          { text: 'cache',        link: '/reference/cache' },
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
      {
        text: 'The fobos File',
        collapsed: true,
        items: [
          { text: 'Overview',          link: '/fobos/' },
          { text: 'Complete Example',  link: '/fobos/complete-example' },
          { text: 'Single Mode',       link: '/fobos/single-mode' },
          { text: 'Many Modes',        link: '/fobos/many-modes' },
          { text: 'Templates',         link: '/fobos/templates' },
          { text: 'Variables',         link: '/fobos/variables' },
          { text: 'Rules',             link: '/fobos/rules' },
          { text: 'Intrinsic Rules',   link: '/fobos/intrinsic-rules' },
          { text: 'Project Metadata',  link: '/fobos/project' },
          { text: '[lint] Section',    link: '/fobos/lint' },
        ],
      },
      { text: 'User Configuration', link: '/reference/configuration' },
      { text: 'JSON Output',  link: '/advanced/json-output' },
      { text: 'MCP Tools',    link: '/ai/mcp' },
      { text: 'Lint Rules',   link: '/lint-rules/' },
      { text: 'Compilers',    link: '/guide/compilers' },
    ],
  },
  {
    text: 'Project',
    items: [
      { text: 'Changelog',    link: '/guide/changelog' },
      { text: 'Contributing', link: '/guide/contributing' },
      { text: 'Architecture', link: '/advanced/architecture' },
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
      { text: 'Start here', link: '/guide/', activeMatch: '^/guide/(index|installation|shell-completion)?$' },
      { text: 'Tutorials', link: '/tutorial/', activeMatch: '^/tutorial/' },
      { text: 'Cookbook', link: '/cookbook/', activeMatch: '^/cookbook/' },
      { text: 'Guides', link: '/guide/topics', activeMatch: '^/(advanced|ai)/|^/guide/topics' },
      { text: 'Concepts', link: '/concepts/build', activeMatch: '^/concepts/' },
      { text: 'Reference', link: '/reference/', activeMatch: '^/(reference|fobos|lint-rules)/' },
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
