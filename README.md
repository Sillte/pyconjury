# pyconjury

`pyconjury` installs GitHub packages that publish Agent Skills through their
Python CLI commands.

## Install

```console
pyconjury install https://github.com/owner/repository
```

The repository must have a `[project.scripts]` table in `pyproject.toml`.
A `SKILL.md` is treated as public when it invokes one of those commands using
`uvx <command>` or `uv tool run <command>`.

Installation clones or updates the repository, installs its CLI commands with
`uv tool install`, writes package metadata as TOML, and links public Skills
under `~/.agents/skills/`. Windows uses directory junctions; other supported
platforms use symbolic links.

Git and uv must be installed. Set `PYCONJURY_HOME` to override the local
repository and metadata storage directory. `MYSKILL_HOME` remains supported as
a legacy setting.


