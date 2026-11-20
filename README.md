# Software factory marketplace

A one-plugin Claude Code marketplace for the **software factory**: issues and
specs in, checked and reviewed draft merge requests out, documentation
included. Nothing merges without a person.

Install it once per machine; every repo and workspace then has
`/factory:setup`, `/factory:vision`, `/factory:run` and `/factory:docs`, with
`fx` on the PATH inside Claude Code.

## Install

1. Put this folder somewhere Claude Code can read it: a git repository
   (GitLab or GitHub, private is fine) or a local folder.
2. Add the marketplace and install the plugin, from a terminal:

   ```
   claude plugin marketplace add <git URL, owner/repo, or path to this folder>
   claude plugin install factory@software-factory
   ```

   or inside Claude Code with `/plugin`.
3. Requirements on the machine: Python 3.9+, git 2.38+, and `glab` (GitLab) or
   `gh` (GitHub) logged in for the projects that use them. Jira at work goes
   through the Atlassian MCP, so no Jira token is needed.
4. In each project, open Claude Code in the repo (or the workspace folder that
   holds several repos) and run `/factory:setup`.

## Update

Edit the plugin here, bump `version` in `plugins/factory/.claude-plugin/plugin.json`
(other machines only pick up a new version string), push, then on each machine:

```
claude plugin marketplace update software-factory
claude plugin update factory@software-factory
```

Project state (`factory/config.json`, checks, jobs, briefs, specs) lives in
each project and is untouched by updates.

## Layout

```
.claude-plugin/marketplace.json
plugins/factory/
  .claude-plugin/plugin.json
  bin/fx            the state machine (Python, stdlib only); on the PATH
  bin/fx-guard      fast PreToolUse hook entry
  hooks/hooks.json  the guard for factory agents
  skills/           run, vision, setup, docs  ->  /factory:<name>
  agents/           intake, planner, spec-writer, builder, reviewers, docs, Jira bridge
  tests/            python3 -m unittest discover -s tests   (from plugins/factory)
```

See `plugins/factory/README.md` for how it works.
