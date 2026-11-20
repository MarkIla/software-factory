# factory

A local software factory for Claude Code: ideas, tickets and spec files in;
checked, reviewed and documented draft merge requests out. You approve the
plan and every Jira write, and you do the merging.

| Command | What it does |
| --- | --- |
| `/factory:setup` | Sets up the factory in this repo or multi-repo workspace |
| `/factory:vision` | Turns an idea into reviewed specs and a central plan you approve, then queues it |
| `/factory:run` | Works the queue and ends by asking you to approve its Jira writes |
| `/factory:docs` | Publishes documentation drafts once their merge requests have merged |

`fx`, the state machine behind these commands, is on your PATH inside Claude
Code; `fx --help` lists its commands.

Full documentation lives with the repository:

- [Getting started](https://github.com/MarkIla/software-factory/blob/main/docs/getting-started.md)
- [How it works](https://github.com/MarkIla/software-factory/blob/main/docs/how-it-works.md)
- [Commands](https://github.com/MarkIla/software-factory/blob/main/docs/commands.md)
- [Configuration](https://github.com/MarkIla/software-factory/blob/main/docs/configuration.md)
- [Development](https://github.com/MarkIla/software-factory/blob/main/docs/development.md)
