import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence
from urllib.parse import parse_qs, quote, unquote, urlsplit, urlunsplit

from pyconjury.models.errors import PyConjuryError

_COMPONENT_PATTERN = re.compile(r"[A-Za-z0-9_.-]+\Z")
_SCP_URL_PATTERN = re.compile(r"git@github\.com:([^?#]+)\Z", re.IGNORECASE)


def _decode_component(component: str) -> str:
    try:
        return unquote(component, errors="strict")
    except UnicodeDecodeError as error:
        raise PyConjuryError("GitHub URL contains invalid percent-encoding.") from error


def _parse_github_fragment(fragment: str) -> dict[str, str]:
    if not fragment:
        return {}
    try:
        values = parse_qs(fragment, keep_blank_values=True, strict_parsing=True)
    except ValueError as error:
        raise PyConjuryError("GitHub URL fragment must use subdirectory=<package-path>.") from error
    if set(values) != {"subdirectory"} or len(values["subdirectory"]) != 1:
        raise PyConjuryError("GitHub URL fragment may only specify one subdirectory.")
    return {"subdirectory": values["subdirectory"][0]}


def _parse_subdirectory(components: Sequence[str]) -> Path:
    parts = [part for component in components for part in component.split("/")]
    if any(not part or part in (".", "..") or "\\" in part for part in parts):
        raise PyConjuryError("GitHub package path must stay inside the repository.")
    subdirectory = Path(*parts)
    if subdirectory.is_absolute() or subdirectory.drive:
        raise PyConjuryError("GitHub package path must stay inside the repository.")
    return subdirectory


@dataclass(frozen=True)
class _GitHubPackageSource:
    requested_url: str
    repository_url: str
    owner: str
    name: str
    revision: str | None = None
    subdirectory: Path | None = None

    @property
    def package_key(self) -> str:
        if self.revision is None and self.subdirectory is None:
            return self.name
        key = self.name
        if self.revision is not None:
            key += f"--ref-{quote(self.revision, safe='')}"
        if self.subdirectory is not None:
            key += f"--{quote(self.subdirectory.as_posix(), safe='')}"
        return key

    @property
    def tool_source(self) -> str:
        if self.revision is None and self.subdirectory is None:
            return self.requested_url

        repository_url = self.repository_url
        if repository_url.lower().startswith("git@github.com:"):
            repository_path = repository_url.split(":", maxsplit=1)[1]
            repository_url = f"ssh://git@github.com/{repository_path}"
        if self.revision is not None:
            repository_url += f"@{quote(self.revision, safe='/')}"

        tool_source = f"git+{repository_url}"
        if self.subdirectory is not None:
            tool_source += f"#subdirectory={quote(self.subdirectory.as_posix(), safe='/')}"
        return tool_source

    def package_folder(self, repository_folder: Path) -> Path:
        if self.subdirectory is None:
            return repository_folder
        return repository_folder / self.subdirectory

    def checkout_folder(self, github_folder: Path) -> Path:
        if self.revision is None:
            return github_folder / self.name
        return github_folder / "_refs" / self.name / quote(self.revision, safe="")


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
        source = self.parse_package_url(url)
        repo_folder = source.checkout_folder(self.root_folder)
        if os.path.lexists(repo_folder):
            self._verify_origin(repo_folder, source.owner, source.name)
            if source.revision is not None:
                self._ensure_clean(repo_folder)
                self._checkout_revision(repo_folder, source.revision)
            if update:
                self._update(repo_folder)
            return repo_folder

        try:
            repo_folder.parent.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise PyConjuryError(f"Cannot create repository storage {self.root_folder}: {error}") from error
        self._run_git("clone", "--", source.repository_url, str(repo_folder), cwd=self.root_folder)
        if source.revision is not None:
            self._checkout_revision(repo_folder, source.revision)
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
        self._ensure_clean(repo_folder)
        branch = self._run_git("-C", str(repo_folder), "branch", "--show-current")
        if not branch:
            self._run_git("-C", str(repo_folder), "fetch", "--all", "--prune")
            return
        self._run_git("-C", str(repo_folder), "pull", "--ff-only")

    def _ensure_clean(self, repo_folder: Path) -> None:
        status = self._run_git("-C", str(repo_folder), "status", "--porcelain", "--untracked-files=all")
        if status:
            raise PyConjuryError(f"Cannot update {repo_folder}: the repository has local changes.")

    def _checkout_revision(self, repo_folder: Path, revision: str) -> None:
        if revision.startswith("-"):
            raise PyConjuryError("GitHub URL must include a valid branch, tag, or commit.")
        self._run_git("-C", str(repo_folder), "checkout", revision)

    @staticmethod
    def _parse_github_url(url: str) -> tuple[str, str, str]:
        source = GitHubLocalStorage.parse_package_url(url)
        if source.revision is not None or source.subdirectory is not None:
            raise PyConjuryError("GitHub repository origin must identify exactly one owner/repository pair.")
        return source.repository_url, source.owner, source.name

    @staticmethod
    def parse_package_url(url: str) -> _GitHubPackageSource:
        clean_url = url.removeprefix("git+")
        scp_match = _SCP_URL_PATTERN.fullmatch(clean_url)
        if scp_match:
            raw_components = scp_match.group(1).rstrip("/").split("/")
            components = [_decode_component(component) for component in raw_components]
            repository_url = clean_url
            if len(components) != 2:
                raise PyConjuryError("SCP-style GitHub URLs must identify exactly one owner/repository pair.")
            revision = None
            subdirectory = None
        else:
            parsed = urlsplit(clean_url)
            if (
                parsed.scheme not in ("https", "ssh")
                or parsed.hostname is None
                or parsed.hostname.casefold() != "github.com"
                or parsed.query
                or (parsed.username is not None and (parsed.scheme != "ssh" or parsed.username != "git"))
            ):
                raise PyConjuryError("GitHub URL must be an HTTPS or SSH repository URL on github.com.")

            path_components = parsed.path.strip("/").split("/")
            if len(path_components) < 2:
                raise PyConjuryError("GitHub URL must identify an owner/repository pair.")

            components = [_decode_component(component) for component in path_components]
            owner = components[0]
            revision: str | None = None
            subdirectory: Path | None = None
            fragment = _parse_github_fragment(parsed.fragment)

            if len(components) >= 3 and components[2] == "tree":
                if fragment:
                    raise PyConjuryError("GitHub tree URLs cannot also specify a URL fragment.")
                if len(components) < 4:
                    raise PyConjuryError("GitHub tree URL must include a branch or tag.")
                revision = components[3]
                if not revision or revision in (".", "..") or "\\" in revision:
                    raise PyConjuryError("GitHub tree URL must include a valid branch or tag.")
                if len(components) > 4:
                    subdirectory = _parse_subdirectory(components[4:])
                repository_name = components[1]
            else:
                repository_name, separator, revision_suffix = components[1].partition("@")
                if separator:
                    revision_parts = [revision_suffix, *components[2:]]
                    revision = "/".join(part for part in revision_parts if part)
                    if not revision or "\\" in revision:
                        raise PyConjuryError("GitHub URL must include a valid branch, tag, or commit.")
                elif len(components) > 2:
                    raise PyConjuryError(
                        "GitHub URL must identify a repository or use a subdirectory fragment."
                    )

                if "subdirectory" in fragment:
                    subdirectory = _parse_subdirectory([fragment["subdirectory"]])
                elif fragment:
                    raise PyConjuryError("GitHub URL fragment may only specify a subdirectory.")

            name = repository_name.removesuffix(".git")
            if any(
                not _COMPONENT_PATTERN.fullmatch(component) or component in (".", "..")
                for component in (owner, name)
            ):
                raise PyConjuryError("GitHub URL must identify a valid owner/repository pair.")

            repository_path = f"/{path_components[0]}/{quote(name, safe='.-_')}"
            repository_url = urlunsplit(
                parsed._replace(path=repository_path, query="", fragment="")
            )

        if scp_match:
            owner = components[0]
            name = components[1].removesuffix(".git")
            if any(
                not _COMPONENT_PATTERN.fullmatch(component) or component in (".", "..")
                for component in (owner, name)
            ):
                raise PyConjuryError("GitHub URL must identify a valid owner/repository pair.")

        return _GitHubPackageSource(
            requested_url=url,
            repository_url=repository_url,
            owner=owner,
            name=name,
            revision=revision,
            subdirectory=subdirectory,
        )

    @staticmethod
    def package_folder(github_folder: Path, url: str) -> Path:
        source = GitHubLocalStorage.parse_package_url(url)
        return source.package_folder(source.checkout_folder(github_folder))

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
