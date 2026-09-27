from __future__ import annotations

import shutil
import subprocess
import uuid
import zipfile
from pathlib import Path
from urllib.parse import urlparse


PROJECT_ROOT = Path(__file__).resolve().parent.parent
WORKSPACES_DIR = PROJECT_ROOT / "workspaces"


class RepositoryManagerError(Exception):
    """Base exception for repository management errors."""


class InvalidRepositoryURLError(RepositoryManagerError):
    """Raised when a repository URL is invalid or unsupported."""


class InvalidRevisionError(RepositoryManagerError):
    """Raised when a Git branch, tag, or commit cannot be resolved."""


class RepositoryCloneError(RepositoryManagerError):
    """Raised when a Git repository cannot be cloned or prepared."""


class ZipExtractionError(RepositoryManagerError):
    """Raised when a ZIP project cannot be safely extracted."""


def _ensure_workspaces_directory() -> None:
    """Create the workspaces directory if it does not exist."""
    WORKSPACES_DIR.mkdir(parents=True, exist_ok=True)


def _validate_session_id(session_id: str) -> str:
    """Validate a NoRepeat session identifier."""
    session_id = session_id.strip()

    if not session_id:
        raise RepositoryManagerError("Session ID cannot be empty.")

    if not session_id.replace("-", "").replace("_", "").isalnum():
        raise RepositoryManagerError("Invalid session ID.")

    return session_id


def create_session_id() -> str:
    """Generate a unique identifier for a NoRepeat analysis session."""
    return uuid.uuid4().hex


def create_session_workspace(
    session_id: str | None = None,
) -> tuple[str, Path]:
    """Create an isolated workspace for a NoRepeat analysis session."""
    _ensure_workspaces_directory()

    if session_id is None:
        session_id = create_session_id()
    else:
        session_id = _validate_session_id(session_id)

    workspace_path = WORKSPACES_DIR / session_id

    if workspace_path.exists():
        raise RepositoryManagerError(
            f"Workspace for session '{session_id}' already exists."
        )

    workspace_path.mkdir(parents=True)
    return session_id, workspace_path


def get_session_repository_path(session_id: str) -> Path:
    """Return the normalized repository path for an existing session."""
    session_id = _validate_session_id(session_id)
    repository_path = (WORKSPACES_DIR / session_id / "repository").resolve()
    workspaces_root = WORKSPACES_DIR.resolve()

    try:
        repository_path.relative_to(workspaces_root)
    except ValueError as exc:
        raise RepositoryManagerError(
            "Repository path resolved outside the allowed workspace directory."
        ) from exc

    if not repository_path.exists() or not repository_path.is_dir():
        raise RepositoryManagerError(
            f"No repository exists for session '{session_id}'."
        )

    return repository_path


def validate_github_url(repository_url: str) -> str:
    """Validate and normalize a public HTTPS GitHub repository URL."""
    repository_url = repository_url.strip()

    if not repository_url:
        raise InvalidRepositoryURLError("Repository URL cannot be empty.")

    parsed = urlparse(repository_url)

    if parsed.scheme != "https":
        raise InvalidRepositoryURLError(
            "Only HTTPS GitHub repository URLs are supported."
        )

    if parsed.netloc.lower() != "github.com":
        raise InvalidRepositoryURLError(
            "Only public GitHub repositories are supported in the MVP."
        )

    path_parts = [part for part in parsed.path.split("/") if part]

    if len(path_parts) != 2:
        raise InvalidRepositoryURLError(
            "Repository URL must use the format "
            "'https://github.com/owner/repository'."
        )

    owner, repository = path_parts

    if repository.endswith(".git"):
        repository = repository[:-4]

    if not owner or not repository:
        raise InvalidRepositoryURLError(
            "Repository owner and repository name are required."
        )

    return f"https://github.com/{owner}/{repository}.git"


def validate_revision(revision: str | None) -> str | None:
    """Validate a user-provided branch, tag, or commit reference."""
    if revision is None:
        return None

    revision = revision.strip()

    if not revision:
        return None

    if len(revision) > 256:
        raise InvalidRevisionError("Revision is too long.")

    if revision.startswith("-"):
        raise InvalidRevisionError("Revision cannot start with '-'.")

    if any(ord(character) < 32 for character in revision):
        raise InvalidRevisionError("Revision contains invalid control characters.")

    return revision


def _check_git_available() -> None:
    """Verify that Git is installed and available in PATH."""
    try:
        subprocess.run(
            ["git", "--version"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.SubprocessError) as exc:
        raise RepositoryCloneError(
            "Git is not installed or is not available in PATH."
        ) from exc


def _run_git(
    repository_path: Path,
    arguments: list[str],
    *,
    timeout: int = 30,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run a Git command against a repository without using a shell."""
    command = ["git", "-C", str(repository_path), *arguments]

    try:
        return subprocess.run(
            command,
            check=check,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise RepositoryCloneError(
            f"Git command exceeded the {timeout}-second timeout."
        ) from exc
    except subprocess.CalledProcessError as exc:
        message = (exc.stderr or exc.stdout or "Unknown Git error.").strip()
        raise RepositoryCloneError(message) from exc


def get_commit_sha(repository_path: Path) -> str:
    """Return the current Git commit SHA for a repository."""
    result = _run_git(
        repository_path,
        ["rev-parse", "HEAD"],
        timeout=15,
    )

    commit_sha = result.stdout.strip()

    if not commit_sha:
        raise RepositoryCloneError(
            "Unable to determine the repository commit SHA."
        )

    return commit_sha


def get_default_branch(repository_path: Path) -> str | None:
    """Return the remote default branch name when it can be determined."""
    result = _run_git(
        repository_path,
        ["symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD"],
        timeout=15,
        check=False,
    )

    if result.returncode != 0:
        return None

    value = result.stdout.strip()

    if value.startswith("origin/"):
        return value[len("origin/") :]

    return value or None


def _try_resolve_revision(
    repository_path: Path,
    revision: str,
) -> str | None:
    """Resolve a revision to a commit SHA using local and origin refs."""
    if revision.startswith("origin/"):
        candidates = [revision]
    else:
        # Prefer the freshly fetched remote branch when both a local branch and
        # origin/<branch> exist. This prevents stale local refs from winning.
        candidates = [f"origin/{revision}", revision]

    for candidate in candidates:
        result = _run_git(
            repository_path,
            ["rev-parse", "--verify", "--quiet", f"{candidate}^{{commit}}"],
            timeout=15,
            check=False,
        )

        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()

    return None


def checkout_repository_revision(
    repository_path: Path,
    revision: str | None,
    *,
    fetch_if_missing: bool = True,
) -> dict:
    """
    Checkout a branch, tag, or commit as a detached candidate snapshot.

    A detached checkout keeps NoRepeat focused on the exact revision being
    audited and avoids mutating the user's branch history.
    """
    requested_revision = validate_revision(revision)

    if requested_revision is None:
        commit_sha = get_commit_sha(repository_path)
        return {
            "requested_revision": None,
            "resolved_revision": "HEAD",
            "commit_sha": commit_sha,
        }

    # Always refresh remote refs before resolving a user-selected revision.
    # Resolving the local ref first can leave NoRepeat pinned to a stale branch
    # after new commits are pushed to GitHub.
    if fetch_if_missing:
        _run_git(
            repository_path,
            ["fetch", "--all", "--prune", "--tags"],
            timeout=120,
        )

    commit_sha = _try_resolve_revision(
        repository_path,
        requested_revision,
    )

    if commit_sha is None:
        raise InvalidRevisionError(
            f"Unable to resolve revision '{requested_revision}'. "
            "Use a branch, tag, or commit SHA that exists in the repository."
        )

    _run_git(
        repository_path,
        ["checkout", "--detach", "--force", commit_sha],
        timeout=30,
    )

    return {
        "requested_revision": requested_revision,
        "resolved_revision": commit_sha,
        "commit_sha": commit_sha,
    }


def clone_github_repository(
    repository_url: str,
    revision: str | None = None,
    session_id: str | None = None,
) -> dict:
    """
    Clone a public GitHub repository and prepare the exact revision to audit.
    """
    _check_git_available()

    normalized_url = validate_github_url(repository_url)
    requested_revision = validate_revision(revision)
    session_id, workspace_path = create_session_workspace(session_id)
    repository_path = workspace_path / "repository"

    try:
        subprocess.run(
            [
                "git",
                "clone",
                "--no-tags",
                normalized_url,
                str(repository_path),
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=180,
        )

        default_branch = get_default_branch(repository_path)
        revision_metadata = checkout_repository_revision(
            repository_path,
            requested_revision,
            fetch_if_missing=True,
        )

        return {
            "success": True,
            "session_id": session_id,
            "source_type": "github",
            "source": normalized_url,
            "repository_path": str(repository_path.resolve()),
            "requested_revision": revision_metadata["requested_revision"],
            "resolved_revision": revision_metadata["resolved_revision"],
            "commit_sha": revision_metadata["commit_sha"],
            "default_branch": default_branch,
            "supports_revision_switching": True,
        }

    except subprocess.TimeoutExpired as exc:
        shutil.rmtree(workspace_path, ignore_errors=True)
        raise RepositoryCloneError(
            "Repository cloning exceeded the allowed time limit."
        ) from exc
    except subprocess.CalledProcessError as exc:
        shutil.rmtree(workspace_path, ignore_errors=True)
        error_message = (
            exc.stderr.strip()
            if exc.stderr
            else "Unknown Git error."
        )
        raise RepositoryCloneError(
            f"Unable to clone repository: {error_message}"
        ) from exc
    except Exception:
        shutil.rmtree(workspace_path, ignore_errors=True)
        raise


def switch_session_revision(
    session_id: str,
    revision: str,
) -> dict:
    """Switch an existing GitHub session to another candidate revision safely.

    The requested revision is resolved *before* destructive cleanup. This means
    a typo or nonexistent branch cannot wipe generated files while leaving the
    manifest pointing at the previous candidate.
    """
    _check_git_available()
    repository_path = get_session_repository_path(session_id)

    if not (repository_path / ".git").exists():
        raise InvalidRevisionError(
            "Revision switching is available only for Git repositories."
        )

    requested_revision = validate_revision(revision)
    if requested_revision is None:
        raise InvalidRevisionError("A branch, tag, or commit is required.")

    # Refresh remote refs first, but do not touch the current working tree yet.
    _run_git(
        repository_path,
        ["fetch", "--all", "--prune", "--tags"],
        timeout=120,
    )

    commit_sha = _try_resolve_revision(repository_path, requested_revision)
    if commit_sha is None:
        raise InvalidRevisionError(
            f"Unable to resolve revision '{requested_revision}'. "
            "The current session was left unchanged. Use a branch, tag, or "
            "commit SHA that exists in the repository."
        )

    # Only after the new revision is known to exist do we clean the disposable
    # audit clone. This removes Bob-generated tests, pytest caches and any
    # remediation changes from the previous candidate.
    head_check = _run_git(
        repository_path,
        ["rev-parse", "--verify", "HEAD"],
        timeout=15,
        check=False,
    )
    if head_check.returncode == 0:
        _run_git(repository_path, ["reset", "--hard", "HEAD"], timeout=30)

    _run_git(repository_path, ["clean", "-fdx"], timeout=30)
    _run_git(
        repository_path,
        ["checkout", "--detach", "--force", commit_sha],
        timeout=30,
    )

    return {
        "success": True,
        "session_id": session_id,
        "repository_path": str(repository_path),
        "requested_revision": requested_revision,
        "resolved_revision": requested_revision,
        "commit_sha": commit_sha,
    }

def _is_zip_symlink(zip_info: zipfile.ZipInfo) -> bool:
    """Return True if a ZIP entry represents a symbolic link."""
    file_type = (zip_info.external_attr >> 16) & 0o170000
    return file_type == 0o120000


def _safe_extract_zip(zip_path: Path, destination: Path) -> None:
    """Safely extract a ZIP file while preventing traversal and symlinks."""
    destination = destination.resolve()

    try:
        with zipfile.ZipFile(zip_path, "r") as archive:
            for member in archive.infolist():
                if _is_zip_symlink(member):
                    raise ZipExtractionError(
                        "Symbolic links are not allowed in ZIP uploads: "
                        f"{member.filename}"
                    )

                target_path = (destination / member.filename).resolve()

                try:
                    target_path.relative_to(destination)
                except ValueError as exc:
                    raise ZipExtractionError(
                        f"Unsafe path detected in ZIP file: {member.filename}"
                    ) from exc

            archive.extractall(destination)

    except zipfile.BadZipFile as exc:
        raise ZipExtractionError(
            "The uploaded file is not a valid ZIP archive."
        ) from exc


def _detect_project_root(extraction_directory: Path) -> Path:
    """Detect a single top-level project directory after ZIP extraction."""
    entries = [
        item
        for item in extraction_directory.iterdir()
        if item.name not in {"__MACOSX", ".DS_Store"}
    ]

    directories = [item for item in entries if item.is_dir()]
    files = [item for item in entries if item.is_file()]

    if len(directories) == 1 and not files:
        return directories[0]

    return extraction_directory


def extract_zip_repository(
    zip_path: str | Path,
    session_id: str | None = None,
) -> dict:
    """
    Extract a ZIP snapshot into a normalized NoRepeat repository workspace.

    ZIP uploads represent a snapshot, so there is no Git revision to switch.
    """
    source_zip = Path(zip_path).resolve()

    if not source_zip.exists():
        raise ZipExtractionError(
            f"ZIP file does not exist: {source_zip}"
        )

    if not source_zip.is_file():
        raise ZipExtractionError(
            "The provided ZIP path is not a file."
        )

    if source_zip.suffix.lower() != ".zip":
        raise ZipExtractionError(
            "Only .zip project uploads are supported."
        )

    session_id, workspace_path = create_session_workspace(session_id)
    extraction_directory = workspace_path / "_zip_extract"
    repository_path = workspace_path / "repository"
    extraction_directory.mkdir(parents=True)

    try:
        _safe_extract_zip(source_zip, extraction_directory)
        detected_root = _detect_project_root(extraction_directory)

        if detected_root == extraction_directory:
            extraction_directory.rename(repository_path)
        else:
            shutil.move(str(detected_root), str(repository_path))
            shutil.rmtree(extraction_directory, ignore_errors=True)

        return {
            "success": True,
            "session_id": session_id,
            "source_type": "zip",
            "source": source_zip.name,
            "repository_path": str(repository_path.resolve()),
            "requested_revision": None,
            "resolved_revision": "uploaded-snapshot",
            "commit_sha": None,
            "default_branch": None,
            "supports_revision_switching": False,
        }

    except Exception:
        shutil.rmtree(workspace_path, ignore_errors=True)
        raise


def remove_session_workspace(session_id: str) -> bool:
    """Remove a NoRepeat session workspace."""
    session_id = _validate_session_id(session_id)
    workspace_path = WORKSPACES_DIR / session_id

    if not workspace_path.exists():
        return False

    shutil.rmtree(workspace_path)
    return True
