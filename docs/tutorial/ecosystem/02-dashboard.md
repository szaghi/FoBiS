---
title: 2. The dashboard
---

# 2. The dashboard

What needs attention, across all the projects, in one table:

<<< @/examples/output/3-ecosystem/02/dashboard.txt{console}

| Column | Says |
|---|---|
| Tree | uncommitted changes |
| Upstream | commits not pushed, or not pulled |
| Version / tag | the project's version (its `VERSION` file, else a literal fobos `[project] version`), and the latest tag |
| Unreleased | commits since the tag, and the release they call for, from their Conventional Commits types: `core` has a `feat` (a minor bump); `mathx` only a `docs` commit, which releases nothing |
| CI | the GitHub Actions result at HEAD (`--no-ci` skips the query, as here: the demo is not on GitHub) |
| Drift | boilerplate files that differ from FoBiS's templates (chapter 5) |
| Pins | the dependencies whose locked commit is behind the dependency's head: `mathx` and `app` still build against the `core` of their last fetch |

The same facts for a script, `--json` (one object per project):

<<< @/examples/output/3-ecosystem/02/json.txt{console}

and as a web page with the dependency graph, `--format html` (opened in the browser without `--no-open`):

<<< @/examples/output/3-ecosystem/02/html.txt{console}

![the HTML dashboard](/images/ecosystem-dashboard-light.png)

![fobis ecosystem graph and dashboard](/gifs/09_ecosystem_dashboard.gif)

*The demo ecosystem of this track: core, mathx, app.*

::: tip What you learned
`fobis ecosystem dashboard`, terminal, JSON and HTML; what each column means. The HTML themes and colours are in the
[ecosystem guide](/cookbook/ecosystem#the-dashboard-as-json-and-as-a-web-page).
:::

Next: [3. Acting on every project](./03-exec).
