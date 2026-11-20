# Configuration

Each project has its own `factory/config.json`, written by `/factory:setup`
(or `fx init work|personal`) and checked by `fx doctor`. You only set what
differs from the defaults; anything missing falls back to the defaults
built into `fx` (`DEFAULTS` in `plugins/factory/bin/fx`).

- [Profiles](#profiles)
- [Trackers and forges](#trackers-and-forges)
- [Branches, titles and commits](#branches-titles-and-commits)
- [Models, lanes and reviewers](#models-lanes-and-reviewers)
- [Documentation and house style](#documentation-and-house-style)
- [Paths, limits and labels](#paths-limits-and-labels)
- [Workspaces with several repos](#workspaces-with-several-repos)
- [Company skills](#company-skills)
- [The checks script](#the-checks-script)

## Profiles

| | `work` | `personal` |
| --- | --- | --- |
| `tracker` | `jira-mcp` | `["local", "github"]` |
| `forge` | `gitlab` | `github` |
| Jira writes | `approve_writes: true` (every write waits for you) | no Jira |
| `outputs` | `gitlab-mr`, `atlassian-work`, `implementation-update` | none |
| Branch | `ABC-123-feat/add-export` | `feat/spec-3-add-export` |
| MR title | `ABC-123: Add export` | `Add export` |
| Docs | `CHANGELOG.md`, ADRs in `docs/adr`, a Confluence space | `CHANGELOG.md`, ADRs in `docs/adr` |
| Company skills | Valhalla preset, off until you turn it on | off |

## Trackers and forges

| Key | Default | Meaning |
| --- | --- | --- |
| `tracker` | `jira` | `jira-mcp` (Jira through the Atlassian MCP), `jira` (REST with a token), `github`, `local`, or a list such as `["local", "github"]` |
| `forge` | `gitlab` | `gitlab` or `github` |
| `base_branch` | `main` | The branch merge requests target |
| `remote` | `origin` | The git remote fx pushes to |
| `jira.url` | | Your site, such as `https://acme.atlassian.net`, for links |
| `jira.jql` | | Which tickets may become jobs: the factory's trust boundary |
| `jira.approve_writes` | `false` (`true` in `work`) | Every Jira write waits in the outbox for your approval |
| `jira.mcp_ttl_sec` | `300` | How long the Jira reader's answers are reused |
| `jira.transitions` | all `null` | Workflow status names for `started`, `ready` and `merged`; `null` skips the move |
| `jira.create` | `{"project": "", "issue_type": "Story"}` | Where new stories go |
| `jira.children` | `{"issue_type": "Story", "link": "parent", "fallback_link": "Relates"}` | How an epic's stories link to it; `"epic_link:customfield_…"` for older Jira |
| `jira.deployment`, `jira.email` | `cloud`, empty | REST mode only (`JIRA_EMAIL` and `JIRA_API_TOKEN` in the environment) |
| `gitlab.url`, `gitlab.project` | read from the remote | Set them for self-hosted GitLab when the remote can't tell |
| `gitlab.remove_source_branch` | `true` | Delete the branch when the MR merges |
| `github.repo`, `github.host` | read from the remote | `owner/repo`, and the host for GitHub Enterprise |

## Branches, titles and commits

| Key | Default |
| --- | --- |
| `branch_template` | `{key}-{type}/{slug}` |
| `title_template` | `{key}: {title}` |
| `commit_template` | `{key}: <short summary>` |

Placeholders: `{key}` (`ABC-123`), `{key_lower}`, `{number}` (`123`),
`{ref}` (`#12` for GitHub issues, otherwise the key), `{type}` (`feat`, `fix`
and so on), `{slug}` and `{title}`.

## Models, lanes and reviewers

| Key | Default | Meaning |
| --- | --- | --- |
| `models.intake` | `sonnet` | Intake |
| `models.planner` | `opus` | The central plan and epic plans |
| `models.high_risk_builder` | `sonnet` | Builder for high-risk jobs |
| `models.docs_writer` | `sonnet` | Docs writer |
| `models.tracker` | `haiku` | The Jira reader and writer |
| `lanes.hotfix` | `{"spec": false, "builder": "sonnet", "max_rounds": 2}` | Straight to the builder |
| `lanes.feature` | `{"spec": true, "spec_writer": "opus", "builder": "sonnet", "max_rounds": 3}` | Spec first unless one was approved |
| `code_review` | `{"low": "haiku", "medium": "sonnet", "high": "opus"}` | Code reviewer model by risk |
| `surface_reviewers` | UI: Sonnet, security: Opus, data: Sonnet | Extra reviewers when intake flags that surface |
| `docs.review` | `{"low": "haiku", "medium": "sonnet", "high": "sonnet"}` | Docs reviewer model by risk (features) |
| `docs.review_hotfix` | `false` | Also review docs on hotfixes |
| `max_agent_retries` | `1` | Retries when an agent's file is malformed |
| `prices_usd_per_mtok` | `{}` | Per-model prices, for cost estimates in `/factory:run status` |

## Documentation and house style

| Key | Default | Meaning |
| --- | --- | --- |
| `docs.changelog` | `null` (`CHANGELOG.md` in profiles) | Builders add an entry here |
| `docs.adr_dir` | `null` (`docs/adr` in profiles) | Where ADRs go |
| `docs.paths` | `[]` | Other documentation folders builders keep current |
| `docs.confluence` | `{"space": null, "parent": null}` | Default Confluence location for `/factory:docs` |
| `outputs.mr_skill` | `null` | A skill whose MR title and description format builders follow |
| `outputs.docs_skill` | `null` | A skill whose page templates the docs writer follows and `/factory:docs` publishes through |
| `outputs.ticket_skill` | `null` | A skill `/factory:vision` creates Jira tickets with |
| `outputs.jira_update_format` | `null` | `implementation-update` for Progress, Next, Blockers and Evidence comments |
| `artifacts.story_path` | `null` | Also commit each spec into the repo at this path |

## Paths, limits and labels

| Key | Default | Meaning |
| --- | --- | --- |
| `concurrency` | `2` | Jobs that run at once |
| `gate_timeout_sec` | `1800` | How long the checks may run |
| `ports` | `{"base": 5100, "step": 10}` | Each job gets its own port range, for dev servers in checks |
| `worktree_dir` | `.worktrees` | Where job worktrees live |
| `cleanup_worktrees` | `true` | Remove a job's worktree once it merges |
| `protected_paths` | `factory/**` and the old copied agent files | Builders may not change these; the gate fails if they do |
| `sensitive_paths` | CI files, migrations, deploy, infra, Terraform, Dockerfiles, `.env` | Allowed, but flagged on the MR for you |
| `labels` | `factory`, `factory-needs-info`, `factory-needs-human`, `factory-in-review`, `factory-sensitive` | Tracker labels; `queue` (`factory`) is what puts a ticket in the queue |

## Workspaces with several repos

When `/factory:setup` runs in a folder that holds several git repos, it lists
them under `repos`. A job changes exactly one repo, and intake picks it.

```json
"repos": {
  "backend": {
    "path": "backend",
    "description": "Python API and workers",
    "base_branch": "develop",
    "match": {"components": ["API"], "labels": []}
  },
  "web": {"path": "web", "description": "React front end"}
}
```

| Field | Meaning |
| --- | --- |
| `path` | The repo folder, relative to the workspace |
| `description` | Tells intake and the planner what lives there |
| `base_branch` | This repo's target branch, when it differs |
| `match.components`, `match.labels` | Jira components or labels that pre-select this repo; a `fx-repo-<name>` label (`repo_label_prefix`) always does |
| `checks` | A checks script other than `factory/checks/<name>.sh` |
| `project` | The forge project, when the remote can't tell |

## Company skills

The `skills` section is optional and off by default. The `work` profile
carries a Valhalla preset. `/factory:setup` offers to turn it on for one
workspace, and `/factory:run` turns it on or off when you ask.

| Key | Default | Meaning |
| --- | --- | --- |
| `skills.enabled` | `false` | Turned on and off through `/factory:setup` or `/factory:run` (`fx skills on`/`off`) |
| `skills.mode` | `discover` | Agents also look for other fitting installed skills |
| `skills.enforce` | `true` | Agents must list the pinned skills they applied |
| `skills.roles` | `{}` | Per role, names or glob patterns of skills it must apply, such as `"reviewer-code": ["val-standards-review"]` |
| `skills.library` | Valhalla commands in `work` | `install`, `update`, `verify`, `outdated`, `lock_file` and `protected_paths` |
| `skills.search_paths` | `[".claude/skills"]` | Where installed skills are found |

Ask `/factory:run` what's installed (`fx skills catalog` underneath); pins that match nothing are
skipped, and the next run re-resolves them when the lock file changes.

## The checks script

`factory/checks.sh` (in a workspace, `factory/checks/<repo>.sh`) is the gate.
It runs in the job's worktree on every round and must exit 0 to pass. Keep it
to the fast checks that matter: install if needed, lint, type-check, unit
tests. The factory runs its own copy, so a branch can't weaken it, and
builders run the same script with `fx selfcheck` before they finish.
