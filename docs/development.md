# Development

How to change the plugin, test it and release a new version.

## Layout

```
.claude-plugin/marketplace.json     the marketplace: one plugin, "factory"
docs/                               this documentation (images/ holds the diagrams)
plugins/factory/
  .claude-plugin/plugin.json        name, version, metadata
  bin/fx                            the state machine: Python 3.9+, standard library only, on the PATH in Claude Code
  bin/fx-guard                      fast PreToolUse hook entry; hands factory agents' calls to `fx guard --hook`
  hooks/hooks.json                  registers the guard for Bash, file writes and MCP tools
  skills/run|vision|setup|docs/     the slash commands /factory:run, :vision, :setup, :docs
  agents/*.md                       the twelve agents, run as factory:<name>
  tests/                            unit tests for fx
```

Three rules hold the design together:

- **`fx` decides, agents judge.** Every rule, stage change and outside write
  lives in `fx`. Skills and agents never change state by hand.
- **One file per agent.** Each agent writes one file whose first line is its
  verdict, and replies with that line only. `fx` validates the file and
  retries or escalates.
- **The guard is the boundary.** Anything an agent must not do is enforced in
  `fx guard`, not only asked for in its prompt.

## Work on it locally

Add your clone as a local marketplace:

```
claude plugin marketplace add <path to your clone>
claude plugin install factory@software-factory
```

Claude Code copies the plugin folder as it is on disk, uncommitted edits
included, into `~/.claude/plugins/cache/`, and sessions use that copy. To
apply your edits, reinstall and start a new session:

```
claude plugin uninstall factory@software-factory
claude plugin install factory@software-factory
```

`claude plugin update` doesn't help here: it does nothing until the version
changes. To try edits in one terminal session without reinstalling, start it
with `claude --plugin-dir <path to your clone>/plugins/factory`.

## Test

```
cd plugins/factory
python3 -m unittest discover -s tests
claude plugin validate .
cd ../.. && claude plugin validate .
```

The tests run `fx` against fake trackers and forges in temporary git repos:
lanes, rounds, the gate, the Jira bridge and outbox, the local queue, the
central plan, the docs stage, the guard and the plugin layout. Add a test with
every behaviour change.

## Change common things

| To | Change |
| --- | --- |
| Add an agent | Add its role to `ROLES` in `bin/fx`, write `agents/<role>.md` (frontmatter `name: <role>`, no `hooks` or `permissionMode`, which plugin agents ignore), teach `fx` when to spawn it, and add guard rules if it writes anywhere new |
| Change a default | `DEFAULTS` (or `PROFILES` for `work` and `personal`) in `bin/fx`, plus [Configuration](configuration.md) |
| Change what an agent does | Its `agents/<role>.md`; keep its output format in step with what `fx` parses |
| Change a slash command | `skills/<name>/SKILL.md` |
| Change a diagram | The diagrams come from the "Software Factory: Architecture and How It Works" Claude Doc; edit them there and export new PNGs into `docs/images/` |

## Release a version

1. Bump `version` in `plugins/factory/.claude-plugin/plugin.json` (and
   `VERSION` in `bin/fx`, which `fx version` prints). Keep the version out of
   `marketplace.json`: when both set it, Claude Code uses `plugin.json`
   silently.
2. Run the tests and both validations.
3. Commit and push.

Machines that installed from the repository receive a new copy only when that
version string changes. They update with:

```
claude plugin marketplace update software-factory
claude plugin update factory@software-factory
```

or automatically, once auto-update is on for the marketplace under
`/plugin` → Marketplaces.

## Distribution notes

- **Private repository:** Claude Code clones with the machine's existing git
  credentials and never prompts. `gh auth login` and `gh auth setup-git` set
  that up for GitHub; an SSH key loaded in the agent works for any host.
- **GitLab:** add the marketplace by its full `https://…/repo.git` URL;
  `owner/repo` always means github.com.
- **A team repository:** run `claude plugin marketplace add <source> --scope project`
  there and commit the `.claude/settings.json` it writes; teammates get the
  marketplace when they trust the folder.
- **claude.ai organization settings** reject plugins with a top-level `bin/`
  folder. Distributing that way would mean moving `bin/` to `scripts/` and
  calling `fx` by its full path.
