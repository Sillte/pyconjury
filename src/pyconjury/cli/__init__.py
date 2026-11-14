import click

from pyconjury.models.errors import PyConjuryError
from pyconjury.services.installer_service import ConjuryInstallerService


@click.group()
def main() -> None:
    """Manage Python packages that publish Agent Skills."""


@main.command()
@click.option("--package", "package_name", help="Show Skills for this installed Python project.")
def list(package_name: str | None) -> None:
    """List installed packages and their public Skills."""
    service = ConjuryInstallerService()
    try:
        if package_name is not None:
            skills = service.list_skills(package_name)
            for skill_path in skills:
                click.echo(skill_path.skill_name)
            return
        packages = service.list_packages()
    except PyConjuryError as error:
        raise click.ClickException(str(error)) from error

    if not packages:
        click.echo("No packages installed.")
        return

    for registered_name, package in packages:
        click.echo(registered_name)
        for skill_path in sorted(package.skill_paths, key=lambda path: path.skill_name.casefold()):
            click.echo(f"  {skill_path.skill_name}")


@main.command()
@click.argument("source")
def install(source: str) -> None:
    """Install a package's public Skills and CLI tool from GitHub or a local path."""
    service = ConjuryInstallerService()
    try:
        package_skills = service.install(source)
    except PyConjuryError as error:
        raise click.ClickException(str(error)) from error

    names = ", ".join(sorted(skill_path.skill_name for skill_path in package_skills.skill_paths))
    click.echo(f"Installed public Skills from {source}: {names}")


@main.command()
@click.argument("package")
def uninstall(package: str) -> None:
    """Uninstall a package by its GitHub URL, local path, or project name."""
    service = ConjuryInstallerService()
    try:
        tool_removed = service.uninstall(package)
    except PyConjuryError as error:
        raise click.ClickException(str(error)) from error

    if tool_removed:
        click.echo(f"Uninstalled {package} and removed its public Skills.")
    else:
        click.echo(f"Removed public Skills for {package}; kept the uv tool used by another package.")
