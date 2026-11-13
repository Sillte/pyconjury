import click

from pyconjury.models.errors import PyConjuryError
from pyconjury.services.installer_service import ConjuryInstallerService


@click.group()
def main() -> None:
    """Manage GitHub repositories that publish Agent Skills."""


@main.command()
@click.argument("github_url")
def install(github_url: str) -> None:
    """Install a repository's public Skills and CLI tool from GitHub."""
    service = ConjuryInstallerService()
    try:
        package_skills = service.install_github(github_url)
    except PyConjuryError as error:
        raise click.ClickException(str(error)) from error

    names = ", ".join(sorted(skill_path.skill_name for skill_path in package_skills.skill_paths))
    click.echo(f"Installed public Skills from {github_url}: {names}")
