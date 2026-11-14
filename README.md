# pyconjury

`pyconjury` installs GitHub or local Python packages that publish Agent Skills
through their CLI commands.

## List

```console
pyconjury list
pyconjury list --package project-name
```

The first command lists installed Python projects and their public Skills.
Use `--package` to list only the Skills registered by a project.

## Install

```console
pyconjury install https://github.com/owner/repository
pyconjury install ./path/to/project
```

## Uninstall

```console
pyconjury uninstall https://github.com/owner/repository
pyconjury uninstall ./path/to/project
pyconjury uninstall project-name
```

The project name is the `[project].name` from `pyproject.toml`. Uninstall
removes the registered Skill links, package metadata, and uv tool. If multiple
registrations use the same project name, uninstalling by project name removes
all of them; uninstalling one source keeps the shared uv tool while another
registration still uses it.

The Python project must have a `[project.scripts]` table in `pyproject.toml`.
A `SKILL.md` is treated as public when it invokes one of those commands using
`uvx <command>` or `uv tool run <command>`.

GitHub installation clones or updates the repository. Local installation uses
the project directory as-is and requires a `pyproject.toml`. Both install the
CLI commands with `uv tool install`, write package metadata as TOML, and link
public Skills under `~/.agents/skills/`. Windows uses directory junctions;
other supported platforms use symbolic links.

Git is required for GitHub installation; uv is required for both. Set
`PYCONJURY_HOME` to override the local repository and metadata storage
directory. 


