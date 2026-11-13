import os
import re
import subprocess
from pathlib import Path
from typing import Sequence
from urllib.parse import urlsplit

from pyconjury.models.errors import PyConjuryError

_COMPONENT_PATTERN = re.compile(r"[A-Za-z0-9_.-]+\Z")
_SCP_URL_PATTERN = re.compile(r"git@github\.com:([^?#]+)\Z", re.IGNORECASE)


class GitHubLocalStorage:
    def __init__(self, root_folder: Path):
        self._root_folder = root_folder.expanduser().resolve()
        self._root_folder.mkdir(exist_ok=True, parents=True)

    @property
    def root_folder(self) -> Path:
        return self._root_folder

    @property
    def names(self) -> Sequence[str]:
        if not self.root_folder.is_dir():
            return []
        return sorted(
            path.name
            for path in self.root_folder.iterdir()
            if path.is_dir() and not path.is_symlink() and (path / ".git").exists()
        )

    def fetch(self, url: str, *, update: bool = False) -> Path:
        clean_url, owner, name = self._parse_github_url(url)
        repo_folder = self.root_folder / name
        if os.path.lexists(repo_folder):
            self._verify_origin(repo_folder, owner, name)
            if update:
                self._update(repo_folder)
            return repo_folder

        try:
            self.root_folder.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise PyConjuryError(f"Cannot create repository storage {self.root_folder}: {error}") from error
        self._run_git("clone", "--", clean_url, str(repo_folder), cwd=self.root_folder)
        return repo_folder

    def get_by_name(self, name: str, *, update: bool = False) -> Path:
        if not name or Path(name).name != name or name in (".", ".."):
            raise PyConjuryError(f"Invalid GitHub repository name: {name!r}")
        repo_folder = self.root_folder / name
        if not repo_folder.is_dir() or repo_folder.is_symlink() or not (repo_folder / ".git").exists():
            raise PyConjuryError(f"GitHub repository {name!r} is not present in {self.root_folder}.")
        origin_url = self._remote_url(repo_folder)
        _, _, origin_name = self._parse_github_url(origin_url)
        if origin_name.casefold() != name.casefold():
            raise PyConjuryError(f"Stored repository folder {name!r} does not match its GitHub origin.")
        if update:
            self._update(repo_folder)
        return repo_folder

    def _verify_origin(self, repo_folder: Path, owner: str, name: str) -> None:
        if not repo_folder.is_dir() or repo_folder.is_symlink() or not (repo_folder / ".git").exists():
            raise PyConjuryError(f"A non-repository path already occupies the repository name: {repo_folder}")
        origin_url = self._remote_url(repo_folder)
        try:
            _, origin_owner, origin_name = self._parse_github_url(origin_url)
        except PyConjuryError as error:
            raise PyConjuryError(f"Cannot verify GitHub origin for stored repository {repo_folder}.") from error
        if (origin_owner.casefold(), origin_name.casefold()) != (owner.casefold(), name.casefold()):
            raise PyConjuryError(
                f"Repository-name collision: {repo_folder} contains {origin_owner}/{origin_name}, not {owner}/{name}."
            )

    def _remote_url(self, repo_folder: Path) -> str:
        return self._run_git("-C", str(repo_folder), "remote", "get-url", "origin")

    def _update(self, repo_folder: Path) -> None:
        status = self._run_git("-C", str(repo_folder), "status", "--porcelain", "--untracked-files=all")
        if status:
            raise PyConjuryError(f"Cannot update {repo_folder}: the repository has local changes.")
        self._run_git("-C", str(repo_folder), "pull", "--ff-only")

    @staticmethod
    def _parse_github_url(url: str) -> tuple[str, str, str]:
        clean_url = url.removeprefix("git+")
        scp_match = _SCP_URL_PATTERN.fullmatch(clean_url)
        if scp_match:
            path = scp_match.group(1)
        else:
            parsed = urlsplit(clean_url)
            if (
                parsed.scheme not in ("https", "ssh")
                or parsed.hostname is None
                or parsed.hostname.casefold() != "github.com"
                or parsed.query
                or parsed.fragment
                or (parsed.username is not None and (parsed.scheme != "ssh" or parsed.username != "git"))
            ):
                raise PyConjuryError("GitHub URL must be an HTTPS or SSH repository URL on github.com.")
            path = parsed.path.lstrip("/")

        components = path.rstrip("/").removesuffix(".git").split("/")
        if len(components) != 2 or any(
            not _COMPONENT_PATTERN.fullmatch(component) or component in (".", "..") for component in components
        ):
            raise PyConjuryError("GitHub URL must identify exactly one owner/repository pair.")
        owner, name = components
        return clean_url, owner, name

    @staticmethod
    def _run_git(*args: str, cwd: Path | None = None) -> str:
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=cwd,
                check=True,
                capture_output=True,
                text=True,
                stdin=subprocess.DEVNULL,
                env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
            )
        except FileNotFoundError as error:
            raise PyConjuryError("Git is required to retrieve GitHub repositories but was not found.") from error
        except subprocess.CalledProcessError as error:
            detail = (error.stderr or error.stdout or "").strip()
            raise PyConjuryError(f"Git command failed: {detail or 'no details were reported'}") from error
        return result.stdout.strip()
