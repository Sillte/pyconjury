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

## Doctor

```console
pyconjury doctor
pyconjury doctor --package project-name
pyconjury doctor --skill public-skill
pyconjury doctor --package project-name --skill public-skill
```

Checks registration metadata, package source folders, registered Skill folders
and links, and whether the corresponding CLI tools are installed with uv. The
command reports each inconsistency and exits with a non-zero status if any are
found. `--package` limits checks to that project and its Skills; `--skill`
limits checks to that Skill's folder and link across installed projects.
When both are provided, package-level checks run for the selected project,
along with checks for only the selected Skill.

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


