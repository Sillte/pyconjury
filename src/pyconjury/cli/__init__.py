import click

from pyconjury.models.errors import PyConjuryError
from pyconjury.services.doctor_service import ConjuryDoctorService
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
@click.option("--package", "package_name", help="Check only this installed Python project and its Skills.")
@click.option("--skill", "skill_name", help="Check only this registered Skill.")
def doctor(package_name: str | None, skill_name: str | None) -> None:
    """Check registered packages, Skills, and installed CLI tools for inconsistencies."""
    service = ConjuryDoctorService()
    try:
        issues = service.check(package_name=package_name, skill_name=skill_name)
    except PyConjuryError as error:
        raise click.ClickException(str(error)) from error

    if not issues:
        if package_name is None and skill_name is None:
            click.echo("All registered packages and Skills are consistent.")
        else:
            click.echo("No issues found for the selected package and Skill.")
        return

    click.echo("Installation issues found:")
    for issue in issues:
        click.echo(f"- {issue}")
    raise click.exceptions.Exit(1)


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
@click.argument("source")
def uninstall(source: str) -> None:
    """Uninstall a package by its GitHub URL, local path, or project name."""
    service = ConjuryInstallerService()
    try:
        tool_removed, removed_skill_names = service.uninstall(source)
    except PyConjuryError as error:
        raise click.ClickException(str(error)) from error

    skills = f": {', '.join(removed_skill_names)}" if removed_skill_names else ""
    if tool_removed:
        click.echo(f"Uninstalled {source} and removed its public Skills{skills}.")
    else:
        click.echo(f"Removed public Skills for {source}{skills}; kept the uv tool used by another package.")


@main.group()
def skill() -> None:
    """Manage installed public Skills."""


@skill.command("remove")
@click.argument("skill_name")
def remove_skill(skill_name: str) -> None:
    """Remove a Skill registration while keeping its Python package installed."""
    service = ConjuryInstallerService()
    try:
        service.remove_skill(skill_name)
    except PyConjuryError as error:
        raise click.ClickException(str(error)) from error
    click.echo(f"Removed Skill {skill_name}.")
