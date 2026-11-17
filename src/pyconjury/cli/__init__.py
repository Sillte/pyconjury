from urllib.parse import urlsplit, urlunsplit

import click

from pyconjury.models.errors import PyConjuryError
from pyconjury.services import (
    ConjuryDoctorService,
    ConjuryInstallService,
    ConjuryPackageQueryService,
    ConjuryRemoveSkillService,
    ConjuryUninstallService,
)


@click.group()
def main() -> None:
    """Manage Python packages that publish Agent Skills."""


@main.command()
@click.option("--package", "package_name", help="Show Skills for this installed Python project.")
def list(package_name: str | None) -> None:
    """List installed packages and their public Skills."""
    service = ConjuryPackageQueryService()
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
        if package.package_link.type == "local":
            source = f"local {package.package_link.path}"
        else:
            source = _mask_url_password(package.package_link.url)
        click.echo(f"  source: {source}")
        for skill_path in sorted(package.skill_paths, key=lambda path: path.skill_name.casefold()):
            click.echo(f"  {skill_path.skill_name}")


def _mask_url_password(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.password is None:
        return url

    user_info, separator, host = parsed.netloc.rpartition("@")
    if not separator:
        return url
    username = user_info.partition(":")[0]
    masked_netloc = f"{username}:****@{host}"
    return urlunsplit(parsed._replace(netloc=masked_netloc))


@main.command()
@click.option("--package", "package_name", help="Check only this installed Python project and its Skills.")
@click.option("--skill", "skill_name", help="Check only this registered Skill.")
@click.option("--prune", is_flag=True, help="Remove broken package and Skill registrations when safe.")
@click.option("--dry-run", is_flag=True, help="Show planned removals without changing anything.")
def doctor(package_name: str | None, skill_name: str | None, prune: bool, dry_run: bool) -> None:
    """Check installations and optionally prune broken package or Skill registrations."""
    if dry_run and not prune:
        raise click.UsageError("--dry-run can only be used with --prune.")

    service = ConjuryDoctorService()
    try:
        if prune:
            actions, issues = service.prune(package_name=package_name, skill_name=skill_name, dry_run=dry_run)
        else:
            issues = service.check(package_name=package_name, skill_name=skill_name)
    except PyConjuryError as error:
        raise click.ClickException(str(error)) from error

    if prune:
        if actions:
            click.echo("Prune plan:" if dry_run else "Prune results:")
            for action in actions:
                click.echo(f"- {action}")
        else:
            click.echo("No safe cleanup actions found.")

        if issues:
            click.echo("Issues found:" if dry_run else "Remaining issues:")
            for issue in issues:
                click.echo(f"- {issue}")

        if issues or (dry_run and actions):
            raise click.exceptions.Exit(1)
        return

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
@click.option("--force", is_flag=True, help="Replace this source's existing Skill registration and links.")
def install(source: str, force: bool) -> None:
    """Install a package's public Skills and CLI tool from GitHub or a local path."""
    service = ConjuryInstallService()
    try:
        package_skills = service.install(source, force=force)
    except PyConjuryError as error:
        raise click.ClickException(str(error)) from error

    names = ", ".join(sorted(skill_path.skill_name for skill_path in package_skills.skill_paths))
    click.echo(f"Installed public Skills from {source}: {names}")


@main.command()
@click.argument("source")
def uninstall(source: str) -> None:
    """Uninstall a package by its GitHub URL, local path, or project name."""
    service = ConjuryUninstallService()
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
    service = ConjuryRemoveSkillService()
    try:
        service.remove_skill(skill_name)
    except PyConjuryError as error:
        raise click.ClickException(str(error)) from error
    click.echo(f"Removed Skill {skill_name}.")
