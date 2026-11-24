# pyconjury

**This is an experimental project exploring ways to specify and manage Agent Skills. It is not intended for production use.**

`pyconjury` installs GitHub or local Python packages that publish Agent Skills
through their CLI commands.

A useful strategy for building sophisticated Agent Skills is to package the operations they need as a Python CLI, then describe in the Skill how and when to use those commands. The CLI provides a concrete interface: the package defines the operations, and the Skill explains how to use them.

pyconjury supports this approach for Python packages installed from GitHub or a local project directory. It installs the package's CLI tools with `uv tool install` and links Skills under `~/.agents/skills/` when their SKILL.md contains a reference to a command declared in `[project.scripts]`, using `uvx <command>` or `uv tool run <command>`. For local development, this brings CLI installation and Skill linking into one workflow.

The name combines py (Python) and conjury (conjuring): Skills are like spells, and the package provides the commands they can invoke.

This makes a Skill's intended command interface explicit; it does not by itself sandbox an LLM or restrict actions beyond the tools and permissions available in its runtime.

## List

```console
pyconjury list
pyconjury list --package project-name
```

The first command lists installed Python projects and their public Skills.
Each package includes its source (local path or GitHub URL). Use `--package` to
list only the Skills registered by a project. Passwords embedded in GitHub
URLs are masked in the source display.

## Doctor

```console
pyconjury doctor
pyconjury doctor --package project-name
pyconjury doctor --skill public-skill
pyconjury doctor --package project-name --skill public-skill
pyconjury doctor --prune --dry-run
pyconjury doctor --prune
pyconjury doctor --prune --package project-name
```

Checks registration metadata, package source folders, registered Skill folders
and links, and whether the corresponding CLI tools are installed with uv. The
command reports each inconsistency and exits with a non-zero status if any are
found. `--package` limits checks to that project and its Skills; `--skill`
limits checks to that Skill's folder and link across installed projects.
When both are provided, package-level checks run for the selected project,
along with checks for only the selected Skill.
`--prune --dry-run` previews safe removals; `--prune` applies them. Skill
registrations with a missing Skill folder, `SKILL.md`, or link are removed, or
an unrepairable package registration and its safe-to-remove Skill links are
removed. Package source directories, GitHub checkouts, and uv tools are kept.
Invalid metadata and links that point elsewhere are left for manual repair.
`--package` and `--skill` also limit pruning to the selected registrations.

## Install

```console
pyconjury install https://github.com/owner/repository
pyconjury install "git+https://github.com/owner/monorepo@main#subdirectory=packages/project"
pyconjury install ./path/to/project
pyconjury install --force ./path/to/project
```

`--force` replaces the existing registration and Skill links for the same
source. It does not delete the package source directory or replace registrations
from other sources.

## Uninstall

```console
pyconjury uninstall https://github.com/owner/repository
pyconjury uninstall "git+https://github.com/owner/monorepo@main#subdirectory=packages/project"
pyconjury uninstall ./path/to/project
pyconjury uninstall project-name
```

The project name is the `[project].name` from `pyproject.toml`. Uninstall
removes the registered Skill links, package metadata, and uv tool. If multiple
registrations use the same project name, uninstalling by project name removes
all of them; uninstalling one source keeps the shared uv tool while another
registration still uses it.

## Remove a Skill

```console
pyconjury skill remove public-skill
```

This removes only the Skill link and its registration entry. The package
registration and uv tool remain installed, even when it was the package's last
Skill. `pyconjury doctor` continues to check the package and uv tool.

Skill names must be unique within a package and across installed registrations,
ignoring case.
Before installing the tool or changing Skill links or registration metadata,
installation checks package metadata, Skill names, and link destinations. If an
error occurs during execution, the registration metadata is kept where possible
so `pyconjury doctor` can report incomplete state; use its findings to repair
the installation manually.

The Python project must have a `[project.scripts]` table in `pyproject.toml`.
A `SKILL.md` is treated as public when it invokes one of those commands using
`uvx` or `uv tool run`, optionally with `--from <package>`, or when a fenced
code block contains a line beginning with one of those commands (optionally
preceded by a `$` shell prompt).

GitHub installation clones or updates the repository. Use uv's Git URL syntax
with `#subdirectory=<package-path>` to select a Python package inside a
monorepo; add `@<revision>` before the fragment to select a branch, tag, or
commit. If omitted, the repository's default revision is used. GitHub
`/tree/{branch}/{package-path}` URLs are also accepted. Local installation
uses the project directory as-is and requires a `pyproject.toml`. Both install
the CLI commands with `uv tool install`, write package metadata as TOML, and
link public Skills under `~/.agents/skills/`. Windows uses directory
junctions; other supported platforms use symbolic links.

Git is required for GitHub installation; uv is required for both. Set
`PYCONJURY_HOME` to override the local repository and metadata storage
directory. 


