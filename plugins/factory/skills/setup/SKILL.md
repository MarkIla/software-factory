---
name: setup
description: Set up the software factory in the current repo or multi-repo workspace, or check and repair an existing setup. Use when the user types /factory:setup, wants to start using the factory in a project, or fx says there is no factory here.
argument-hint: "[work | personal]"
---

# Factory setup

You install the factory into one project: a repo, or a workspace folder that
holds several repos. The plugin itself is already installed globally; a
project needs only its own `factory/config.json`, its checks script(s) and a
few permissions. Work in the folder the user opened. Ask only what you can't
find out yourself, and show every file you write before moving on.

Arguments: $ARGUMENTS

`fx` is on your PATH (the plugin's `bin/`).

## You run fx; the user decides

The factory guides the user's workflow. They type slash commands and answer
questions; they never need `fx`.

- Run every `fx` command yourself. Never ask the user to type one, and don't
  show fx commands as instructions to them.
- fx output names follow-up commands (`fx release KEY`, `fx outbox`,
  `fx plan SLUG --file`, `fx feedback KEY`). Those are for you: turn each into
  a short question (AskUserQuestion when you can name the options) and run it
  on their yes.
- Finish every turn that leaves work open with **Next**: the one or two things
  that move the work forward, in order, as a decision to make, a merge request
  to review (with its link) or a slash command (`/factory:vision`,
  `/factory:run`, `/factory:docs`).

## 1. Look around (no questions yet)

- `fx where`: if a factory home already exists here, this is a check-up: skip
  to step 6 (doctor), then fix what it reports.
- `git rev-parse --show-toplevel` and the folder listing: one repo, or a
  workspace of repos (sub-folders with `.git`)?
- Remotes (`git remote -v` in each repo): GitLab or GitHub, and the host.
- `.valhalla.lock`, `_val/`, `.mcp.json`: a work workspace with the company
  skills library and its Atlassian and GitLab MCP servers.
- How the repo builds and tests: `package.json` scripts, `pyproject.toml`,
  `Makefile`, `go.mod`, `Cargo.toml`, `.gitlab-ci.yml` or
  `.github/workflows/*`, `AGENTS.md`/`CLAUDE.md`. Use an Explore subagent for a
  big workspace and keep only the conclusions.
- Old per-project install from the zip: `factory/bin/fx`,
  `.claude/agents/fx-*.md`, `.claude/skills/factory/`, `.claude/skills/vision/`.

## 2. Choose the profile

`work` (Jira through the Atlassian MCP, GitLab, approvals for every Jira
write, the user's gitlab-mr and atlassian-work house style) or `personal`
(local spec queue plus GitHub issues, GitHub pull requests, no Jira). Infer it
from step 1 (GitLab remote or Valhalla → work; GitHub → personal) and confirm
in one question only if it is ambiguous or the argument says otherwise.

## 3. Initialise

Run `fx init <profile>` in the project folder. In a workspace it detects the
repos and writes one checks script per repo. In a single repo it also updates
`.gitignore` with the factory's runtime folders.

If an old `factory/config.json` exists, don't overwrite it: read it, then
move its values onto the new defaults by editing. Keys it lacks fall back to
fx's defaults. A work project on `"tracker": "jira"` (REST with a token): offer
`"jira-mcp"` with `"approve_writes": true`, which needs no token.

## 4. Fill in factory/config.json

Edit only what you can ground; ask for the rest in one AskUserQuestion round.

Work profile:
- `tracker`: keep `jira-mcp`. No Jira token is needed.
- `jira.url`: the Atlassian site (`https://<site>.atlassian.net`) for links.
- `jira.jql`: the factory's trust boundary; only issues it matches can become
  jobs. Usually `project = <KEY> AND labels = factory AND statusCategory != Done`.
- `jira.create.project`, `jira.transitions` (the workflow's status names for
  started and ready, or null to skip).
- `jira.approve_writes`: keep `true` (every Jira write waits for approval).
- `forge`: `gitlab`; `gitlab.host` if self-hosted. GitLab uses `glab` when
  it is logged in, so check `glab auth status`.
- `outputs`: `mr_skill: gitlab-mr`, `docs_skill: atlassian-work`,
  `jira_update_format: implementation-update`. Set `ticket_skill` only if the
  user names a ticket-creation skill they use.
- `docs.confluence.space` and `parent`: where external docs usually go.
- `docs.changelog`, `docs.adr_dir`, `docs.paths`: match what the repo
  already has (an existing `CHANGELOG.md`, `docs/adr`, `doc/decisions`, …).

Personal profile:
- `tracker`: `["local", "github"]`, or `["local"]` for a repo with no GitHub
  remote (then also set `forge` to match where pull requests go).
- `github.repo` if it can't be read from the remote. `gh auth status` must be
  logged in for GitHub.
- `docs` as above.

Both: `base_branch`, `concurrency`, `sensitive_paths` (auth, payments,
migrations, infra), and in a workspace each repo's `description` and
`match.components`/`match.labels`.

## 5. Write the checks

The gate runs `factory/checks.sh` (workspace: `factory/checks/<repo>.sh`) on
every round. It is the factory's copy, so builders can't weaken it. Replace
the template with the repo's real, fast checks: install if needed, lint,
type-check, unit tests. Mirror CI where it is cheap; skip slow end-to-end
suites unless the user wants them. Remove the `FX-UNCONFIGURED` line. Show the
script and run `fx doctor --checks` to see it pass on the base branch.

## 6. Permissions, MCP and skills

- Propose adding to `.claude/settings.local.json` (show it first; merge with
  what is there):
  ```json
  {"permissions": {"allow": [
    "Bash(fx:*)",
    "Edit(//<home>/factory/jobs/**)", "Edit(//<home>/.worktrees/**)",
    "Bash(git status:*)", "Bash(git diff:*)", "Bash(git log:*)",
    "Bash(git add:*)", "Bash(git commit:*)", "Bash(git merge:*)"
  ]}}
  ```
  where `<home>` is the factory home's absolute path without its leading
  slash (`//` marks an absolute path in permission rules), plus the test and
  lint commands from the checks script. Adjust `.worktrees` if `worktree_dir`
  differs. The plugin's guard hook still
  blocks pushes, rebases, protected paths, writes outside a job and every MCP
  write by factory agents, so these allowances stay narrow.
- Work: the Atlassian MCP must be connected in this session (`/mcp`). Valhalla's
  `.mcp.json` usually provides it.
- Valhalla workspace: offer `fx skills on` (optional), then `fx skills catalog`.

## 7. Clean up an old install

If step 1 found the zip install, offer to delete `factory/bin/fx`,
`factory/tests/`, `.claude/agents/fx-*.md`, `.claude/skills/factory/` and
`.claude/skills/vision/`. Keep `factory/config.json`, the checks, `jobs/`,
`briefs/` and `specs/`. Old jobs carry on under the plugin.

## 8. Finish

Run `fx doctor` and fix every FAIL you can. Then tell the user in two or three
lines what's set up, and end with **Next**: `/factory:vision` to shape new
work, `/factory:vision KEY` to start from an existing ticket, `/factory:run`
to build what's queued. `/factory:docs` comes later, once work has merged.
