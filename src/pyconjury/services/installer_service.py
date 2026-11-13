import subprocess
from pathlib import Path

from pyconjury.infra.filesystem_link_creator import create_default_file_system_link_creator
from pyconjury.models.errors import PyConjuryError
from pyconjury.models.links import GithubPackageURL
from pyconjury.models.package_skills import PackageSkills
from pyconjury.models.storage import PyconjuryStorage
from pyconjury.skill_searcher import SkillSearcher


class ConjuryInstallerService:
    def install_github(self, url: str) -> PackageSkills:
        storage = PyconjuryStorage.from_storage_folder()
        repository_folder = storage.github_storage.fetch(url, update=True)
        searcher = SkillSearcher(repository_folder)
        skill_paths = searcher.infer_public_skill_paths()
        link_creator = create_default_file_system_link_creator()
        if not skill_paths:
            raise PyConjuryError(f"No public Skills with an installed CLI command were found in {url}.")

        package_skills = PackageSkills(package_link=GithubPackageURL(url=url), skill_paths=skill_paths)
        package_file = storage.root_folder / f"{repository_folder.name}.toml"
        _check_existing_package_file(package_file, package_skills)
        skills_folder = _agents_skills_folder()
        for skill_path in skill_paths:
            target = repository_folder / skill_path.rel_path
            link_path = skills_folder / skill_path.skill_name
            link_creator.validate_directory_link(target, link_path)

        _install_tool(url)
        for skill_path in skill_paths:
            target = repository_folder / skill_path.rel_path
            link_path = skills_folder / skill_path.skill_name
            link_creator.create_directory_link(target, link_path)

        package_skills.write_toml_file(package_file)
        return package_skills


def _agents_skills_folder() -> Path:
    return Path.home() / ".agents" / "skills"


def _check_existing_package_file(package_file: Path, package_skills: PackageSkills) -> None:
    if not package_file.exists():
        return

    existing_package = PackageSkills.from_toml_file(package_file)
    if existing_package.package_link != package_skills.package_link:
        raise PyConjuryError(f"Cannot replace package metadata for a different GitHub URL: {package_file}")


def _install_tool(url: str) -> None:
    git_url = url.removeprefix("git+")
    if git_url.startswith("git@github.com:"):
        package_url = f"git+ssh://git@github.com/{git_url.removeprefix('git@github.com:')}"
    elif url.startswith("git+"):
        package_url = url
    else:
        package_url = f"git+{git_url}"
    try:
        subprocess.run(
            ["uv", "tool", "install", "--force", "--refresh", package_url],
            check=True,
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
        )
    except FileNotFoundError as error:
        raise PyConjuryError("uv is required to install the GitHub package but was not found.") from error
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or error.stdout or "").strip()
        raise PyConjuryError(f"uv tool install failed: {detail or 'uv reported no details.'}") from error
