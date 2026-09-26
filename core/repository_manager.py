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


class RepositoryCloneError(RepositoryManagerError):
    """Raised when a Git repository cannot be cloned."""


class ZipExtractionError(RepositoryManagerError):
    """Raised when a ZIP project cannot be safely extracted."""


def _ensure_workspaces_directory() -> None:
    """Create the workspaces directory if it does not exist."""
    WORKSPACES_DIR.mkdir(parents=True, exist_ok=True)


def create_session_id() -> str:
    """Generate a unique identifier for a NoRepeat analysis session."""
    return uuid.uuid4().hex


def create_session_workspace(session_id: str | None = None) -> tuple[str, Path]:
    """
    Create an isolated workspace for a NoRepeat analysis session.

    Returns:
        tuple[str, Path]: Session ID and workspace path.
    """
    _ensure_workspaces_directory()

    if session_id is None:
        session_id = create_session_id()

    if not session_id.replace("-", "").replace("_", "").isalnum():
        raise RepositoryManagerError("Invalid session ID.")

    workspace_path = WORKSPACES_DIR / session_id

    if workspace_path.exists():
        raise RepositoryManagerError(
            f"Workspace for session '{session_id}' already exists."
        )

    workspace_path.mkdir(parents=True)

    return session_id, workspace_path


def validate_github_url(repository_url: str) -> str:
    """
    Validate and normalize a public GitHub repository URL.

    Supported example:
        https://github.com/owner/repository
    """
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


def get_commit_sha(repository_path: Path) -> str:
    """Return the current Git commit SHA for a cloned repository."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repository_path), "rev-parse", "HEAD"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=15,
        )

        return result.stdout.strip()

    except subprocess.SubprocessError as exc:
        raise RepositoryCloneError(
            "Unable to determine the repository commit SHA."
        ) from exc


def clone_github_repository(
    repository_url: str,
    session_id: str | None = None,
) -> dict:
    """
    Clone a public GitHub repository into an isolated NoRepeat workspace.

    Returns:
        dict: Metadata about the cloned repository.
    """
    _check_git_available()

    normalized_url = validate_github_url(repository_url)

    session_id, workspace_path = create_session_workspace(session_id)

    repository_path = workspace_path / "repository"

    try:
        subprocess.run(
            [
                "git",
                "clone",
                "--depth",
                "1",
                normalized_url,
                str(repository_path),
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=120,
        )

        commit_sha = get_commit_sha(repository_path)

        return {
            "success": True,
            "session_id": session_id,
            "source_type": "github",
            "source": normalized_url,
            "repository_path": str(repository_path.resolve()),
            "commit_sha": commit_sha,
        }

    except subprocess.TimeoutExpired as exc:
        shutil.rmtree(workspace_path, ignore_errors=True)

        raise RepositoryCloneError(
            "Repository cloning exceeded the allowed time limit."
        ) from exc

    except subprocess.CalledProcessError as exc:
        shutil.rmtree(workspace_path, ignore_errors=True)

        error_message = exc.stderr.strip() if exc.stderr else "Unknown Git error."

        raise RepositoryCloneError(
            f"Unable to clone repository: {error_message}"
        ) from exc


def _is_zip_symlink(zip_info: zipfile.ZipInfo) -> bool:
    """Return True if a ZIP entry represents a symbolic link."""
    file_type = (zip_info.external_attr >> 16) & 0o170000
    return file_type == 0o120000


def _safe_extract_zip(zip_path: Path, destination: Path) -> None:
    """
    Safely extract a ZIP file while preventing path traversal and symlinks.
    """
    destination = destination.resolve()

    try:
        with zipfile.ZipFile(zip_path, "r") as archive:
            for member in archive.infolist():
                if _is_zip_symlink(member):
                    raise ZipExtractionError(
                        f"Symbolic links are not allowed in ZIP uploads: "
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
    """
    Detect the project root after ZIP extraction.

    If the archive contains one top-level directory, that directory is used.
    Otherwise, the extraction directory itself is used.
    """
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
    Extract a ZIP project into an isolated NoRepeat workspace.

    Returns:
        dict: Metadata about the extracted project.
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

    extraction_directory = workspace_path / "repository"
    extraction_directory.mkdir(parents=True)

    try:
        _safe_extract_zip(source_zip, extraction_directory)

        repository_path = _detect_project_root(extraction_directory)

        return {
            "success": True,
            "session_id": session_id,
            "source_type": "zip",
            "source": str(source_zip),
            "repository_path": str(repository_path.resolve()),
            "commit_sha": None,
        }

    except Exception:
        shutil.rmtree(workspace_path, ignore_errors=True)
        raise


def remove_session_workspace(session_id: str) -> bool:
    """
    Remove a NoRepeat session workspace.

    Returns:
        bool: True if a workspace was removed.
    """
    workspace_path = WORKSPACES_DIR / session_id

    if not workspace_path.exists():
        return False

    shutil.rmtree(workspace_path)

    return True