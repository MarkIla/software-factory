# Getting started

This page takes you from nothing installed to your first merged change.
Install the plugin once per machine, set up each project once, then use the
same few commands everywhere.

## 1. Check the machine

| You need | Why | Check with |
| --- | --- | --- |
| Claude Code | Runs the plugin | `claude --version` |
| Python 3.9 or later | `fx`, the factory's state machine, is a Python script with no dependencies | `python3 --version` |
| git 2.38 or later | Worktrees and merge checks | `git --version` |
| `glab`, logged in (GitLab projects) | Pushes branches and opens merge requests | `glab auth status` |
| `gh`, logged in (GitHub projects) | Pushes branches, opens pull requests, reads issues | `gh auth status` |
| The Atlassian MCP (Jira at work) | The factory reads and writes Jira through it, with no API token on your machine | `/mcp` in Claude Code |

## 2. Install the plugin

```
claude plugin marketplace add MarkIla/software-factory
claude plugin install factory@software-factory
claude plugin list
```

The last command shows `factory@software-factory` as enabled. For a private
repository, git must be able to read it without asking for a password first:
`gh auth login` followed by `gh auth setup-git` does that for GitHub.

You can also install from a local folder, such as a clone you are editing:
`claude plugin marketplace add <path to the folder>`. Claude Code installs a
copy of the plugin, so later edits in the folder don't reach your sessions
until you reinstall it. See [Development](development.md#work-on-it-locally).

Everything in a project's `factory/` folder belongs to that project.
Updating or reinstalling the plugin never touches it.

## 3. Set up a project

Open Claude Code in the repo, or in the workspace folder that holds several
repos, and run:

```
/factory:setup
```

Setup looks at the repos, remotes and build files first, then asks only what
it can't find out:

- **Profile.** `work` uses Jira through the Atlassian MCP, GitLab, approvals
  for every Jira write and your `gitlab-mr` and `atlassian-work` styles.
  `personal` uses local spec files and GitHub issues, and GitHub pull
  requests.
- **Config.** It writes `factory/config.json` and fills in what it can ground:
  the Jira site and query, the GitLab host, your changelog and ADR folders.
- **Checks.** It writes `factory/checks.sh` (in a workspace, one script per
  repo under `factory/checks/`) with the repo's real lint, type-check and test
  commands, and runs them once on the base branch.
- **Permissions.** It suggests a few allow rules for
  `.claude/settings.local.json` so runs don't stop for routine commands.
- **Company skills.** In a Valhalla workspace it offers `fx skills on`.
- **Health check.** It ends with `fx doctor` and fixes what it reports.

In a single repo, setup also adds the factory's runtime folders to
`.gitignore`.

## 4. Your first piece of work

### Shape it

```
/factory:vision
```

Describe what you want in as many messages as you like. It plays the idea
back, asks a few questions at a time, checks it against the code, and splits
anything bigger than one merge request into stories. It writes the specs into
`factory/briefs/<name>/`, each with a Documentation section that says which
documents the change needs. Read and edit them; nothing is filed until you
choose.

### Approve the central plan

Still inside `/factory:vision`, the planner (Opus, in its own context) plans
the whole build once:

- **Waves:** stories in the same wave can be built at the same time.
- **Shared contracts:** the data model and interfaces every story builds
  against, decided once and built first.
- **Touch points:** the files each story changes, so collisions show up now.
- **Documentation:** the feature-level documents, such as an overview.

Read `factory/briefs/<name>/plan.md`, then approve it or send it back with
your notes. The plan is then filed in order: the epic first (held, so it's
never built itself), then every story with its spec and dependencies. On Jira,
you approve those creates too.

### Run the factory

```
/factory:run
```

The session becomes the orchestrator. It starts each ticket whose
dependencies have merged, spawns the agents `fx` names, runs your checks and
reports one line per change. Each job ends as a ready merge request, a
question for the reporter, or a job that needs you. At the end of the run it
shows the Jira writes it wants to make in one table, and you approve all,
some or none.

### Merge and publish

Review and merge each ready merge request yourself; the factory never merges.
The next `/factory:run` notices, closes the job and starts the next wave.

When work has merged, publish its documentation drafts:

```
/factory:docs
```

It checks each draft against the merged code and publishes it through your
`atlassian-work` preview and approval (Confluence at work), or files it as a
small docs change in the repo (personal projects).

## Day to day

| You want to | Do this |
| --- | --- |
| Turn an idea into work | `/factory:vision` |
| Build what's queued | `/factory:run` |
| Build one ticket | `/factory:run ABC-123` |
| See where things are | `/factory:run status`, or `/factory:run status ABC-123` |
| Give feedback on a merge request | `/factory:run` and say what to change; it starts a new round |
| Answer a question the factory asked | `/factory:run` and give the answer |
| Approve pending Jira writes | `/factory:run outbox` |
| Publish documentation | `/factory:docs` |
| Check the setup | `fx doctor` |

## Update the plugin

```
claude plugin marketplace update software-factory
claude plugin update factory@software-factory
```

Or turn on auto-update once under `/plugin` → Marketplaces. A machine only
receives a new copy when the plugin's `version` changes; see
[Development](development.md#release-a-version).

## Upgrade from the zip install

If a project still has the copied files from the first, zip-based version,
run `/factory:setup` in it. It keeps `factory/config.json`, the checks, jobs,
briefs and specs, offers to switch Jira to the MCP, and offers to delete
`factory/bin/fx`, `.claude/agents/fx-*.md`, `.claude/skills/factory/` and
`.claude/skills/vision/`.

## When something goes wrong

| Symptom | Likely cause and fix |
| --- | --- |
| `Path does not exist` when adding the marketplace | The path is wrong. Use `~/…` or the full path to the folder holding `.claude-plugin/marketplace.json`, not your project |
| `/factory:…` commands don't appear | Start a new Claude Code session after installing; check `claude plugin list` |
| `fx: no factory/config.json` | Run `/factory:setup` in the repo or workspace first |
| The run keeps asking for a Jira sync | The Atlassian MCP isn't connected in this session; check `/mcp` |
| A Jira write failed | `fx outbox` shows it as failed; `fx outbox retry ID` retries it |
| A job stopped with `needs-human` | `fx status KEY` gives the reason; give feedback with `/factory:run`, fix it yourself, or drop it |
| The gate fails with `checks.sh is not configured yet` | Put the real commands in `factory/checks.sh` and remove the `FX-UNCONFIGURED` line |
| Pushing the plugin repo is rejected (non-fast-forward) | The remote has commits you don't: `git pull origin main --allow-unrelated-histories --no-rebase`, then push |
