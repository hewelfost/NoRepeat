from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from core.repository_manager import WORKSPACES_DIR


# MVP formats.
# PDF and DOCX can be added later when we connect Bob document understanding.
ALLOWED_INCIDENT_EXTENSIONS = {".md", ".txt"}

# Prevent unnecessarily large uploads during the hackathon MVP.
MAX_INCIDENT_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB


class IncidentManagerError(Exception):
    """Base exception for incident management errors."""


class InvalidIncidentFileError(IncidentManagerError):
    """Raised when an incident file is invalid or unsupported."""


class SessionNotFoundError(IncidentManagerError):
    """Raised when a NoRepeat session workspace does not exist."""


def _validate_session_id(session_id: str) -> str:
    """
    Validate a NoRepeat session identifier.

    Args:
        session_id: Session identifier.

    Returns:
        str: Validated session identifier.
    """
    session_id = session_id.strip()

    if not session_id:
        raise IncidentManagerError("Session ID cannot be empty.")

    if not session_id.replace("-", "").replace("_", "").isalnum():
        raise IncidentManagerError("Invalid session ID.")

    return session_id


def get_session_workspace(session_id: str) -> Path:
    """
    Return the workspace path for an existing NoRepeat session.

    Args:
        session_id: NoRepeat session identifier.

    Returns:
        Path: Session workspace path.
    """
    session_id = _validate_session_id(session_id)

    workspace_path = (WORKSPACES_DIR / session_id).resolve()
    workspaces_root = WORKSPACES_DIR.resolve()

    try:
        workspace_path.relative_to(workspaces_root)
    except ValueError as exc:
        raise IncidentManagerError(
            "Session workspace resolved outside the allowed directory."
        ) from exc

    if not workspace_path.exists():
        raise SessionNotFoundError(
            f"No workspace exists for session '{session_id}'."
        )

    if not workspace_path.is_dir():
        raise SessionNotFoundError(
            f"Session workspace '{session_id}' is not a directory."
        )

    return workspace_path


def _sanitize_filename(filename: str) -> str:
    """
    Sanitize and validate an uploaded incident filename.

    Args:
        filename: Original filename.

    Returns:
        str: Safe filename.
    """
    if not filename:
        raise InvalidIncidentFileError(
            "Incident filename cannot be empty."
        )

    safe_name = Path(filename).name.strip()

    if not safe_name:
        raise InvalidIncidentFileError(
            "Incident filename is invalid."
        )

    extension = Path(safe_name).suffix.lower()

    if extension not in ALLOWED_INCIDENT_EXTENSIONS:
        supported = ", ".join(sorted(ALLOWED_INCIDENT_EXTENSIONS))

        raise InvalidIncidentFileError(
            f"Unsupported incident file type '{extension}'. "
            f"Supported types: {supported}."
        )

    return safe_name


def _calculate_sha256(file_path: Path) -> str:
    """
    Calculate the SHA-256 hash of a file.

    Args:
        file_path: File to hash.

    Returns:
        str: SHA-256 hexadecimal digest.
    """
    sha256 = hashlib.sha256()

    with file_path.open("rb") as file:
        for chunk in iter(lambda: file.read(8192), b""):
            sha256.update(chunk)

    return sha256.hexdigest()


def _get_incident_directory(session_id: str) -> Path:
    """
    Return and create the incident directory for a session.

    Structure:
        workspaces/<session_id>/incident/
    """
    workspace_path = get_session_workspace(session_id)

    incident_directory = workspace_path / "incident"
    incident_directory.mkdir(parents=True, exist_ok=True)

    return incident_directory


def save_uploaded_incident(
    session_id: str,
    filename: str,
    content: bytes,
    overwrite: bool = False,
) -> dict:
    """
    Save an uploaded incident report inside an existing NoRepeat session.

    Args:
        session_id: Existing NoRepeat session ID.
        filename: Uploaded filename.
        content: Raw file content.
        overwrite: Allow replacing an existing incident file.

    Returns:
        dict: Metadata about the stored incident.
    """
    if not isinstance(content, bytes):
        raise InvalidIncidentFileError(
            "Incident content must be provided as bytes."
        )

    if not content:
        raise InvalidIncidentFileError(
            "Incident file cannot be empty."
        )

    if len(content) > MAX_INCIDENT_SIZE_BYTES:
        raise InvalidIncidentFileError(
            "Incident file exceeds the 5 MB MVP size limit."
        )

    safe_filename = _sanitize_filename(filename)
    incident_directory = _get_incident_directory(session_id)

    destination = incident_directory / safe_filename

    if destination.exists() and not overwrite:
        raise InvalidIncidentFileError(
            f"Incident file '{safe_filename}' already exists "
            f"for session '{session_id}'."
        )

    destination.write_bytes(content)

    return {
        "success": True,
        "session_id": session_id,
        "filename": safe_filename,
        "incident_path": str(destination.resolve()),
        "file_type": destination.suffix.lower(),
        "size_bytes": destination.stat().st_size,
        "sha256": _calculate_sha256(destination),
    }


def import_incident_file(
    session_id: str,
    source_path: str | Path,
    overwrite: bool = False,
) -> dict:
    """
    Import an existing local incident report into a NoRepeat session.

    Useful during development and controlled demonstrations.

    Args:
        session_id: Existing NoRepeat session ID.
        source_path: Path to the incident file.
        overwrite: Allow replacing an existing incident file.

    Returns:
        dict: Metadata about the imported incident.
    """
    source = Path(source_path).resolve()

    if not source.exists():
        raise InvalidIncidentFileError(
            f"Incident file does not exist: {source}"
        )

    if not source.is_file():
        raise InvalidIncidentFileError(
            "Incident source must be a file."
        )

    safe_filename = _sanitize_filename(source.name)

    file_size = source.stat().st_size

    if file_size == 0:
        raise InvalidIncidentFileError(
            "Incident file cannot be empty."
        )

    if file_size > MAX_INCIDENT_SIZE_BYTES:
        raise InvalidIncidentFileError(
            "Incident file exceeds the 5 MB MVP size limit."
        )

    incident_directory = _get_incident_directory(session_id)
    destination = incident_directory / safe_filename

    if destination.exists() and not overwrite:
        raise InvalidIncidentFileError(
            f"Incident file '{safe_filename}' already exists "
            f"for session '{session_id}'."
        )

    shutil.copy2(source, destination)

    return {
        "success": True,
        "session_id": session_id,
        "filename": safe_filename,
        "incident_path": str(destination.resolve()),
        "file_type": destination.suffix.lower(),
        "size_bytes": destination.stat().st_size,
        "sha256": _calculate_sha256(destination),
    }


def list_incidents(session_id: str) -> list[dict]:
    """
    List incident reports stored in a NoRepeat session.

    Args:
        session_id: Existing NoRepeat session ID.

    Returns:
        list[dict]: Incident metadata.
    """
    incident_directory = _get_incident_directory(session_id)

    incidents: list[dict] = []

    for file_path in sorted(incident_directory.iterdir()):
        if not file_path.is_file():
            continue

        if file_path.suffix.lower() not in ALLOWED_INCIDENT_EXTENSIONS:
            continue

        incidents.append(
            {
                "filename": file_path.name,
                "incident_path": str(file_path.resolve()),
                "file_type": file_path.suffix.lower(),
                "size_bytes": file_path.stat().st_size,
                "sha256": _calculate_sha256(file_path),
            }
        )

    return incidents


def get_incident_path(
    session_id: str,
    filename: str | None = None,
) -> Path:
    """
    Return an incident file path from a session.

    If filename is omitted, exactly one incident must exist.

    Args:
        session_id: Existing NoRepeat session ID.
        filename: Optional incident filename.

    Returns:
        Path: Incident file path.
    """
    incident_directory = _get_incident_directory(session_id)

    if filename is not None:
        safe_filename = _sanitize_filename(filename)
        incident_path = incident_directory / safe_filename

        if not incident_path.exists():
            raise InvalidIncidentFileError(
                f"Incident '{safe_filename}' was not found "
                f"in session '{session_id}'."
            )

        return incident_path.resolve()

    incidents = list_incidents(session_id)

    if not incidents:
        raise InvalidIncidentFileError(
            f"No incident reports exist for session '{session_id}'."
        )

    if len(incidents) > 1:
        raise InvalidIncidentFileError(
            "Multiple incident reports exist in this session. "
            "Specify the filename explicitly."
        )

    return Path(incidents[0]["incident_path"])


def read_incident_text(
    session_id: str,
    filename: str | None = None,
) -> str:
    """
    Read a Markdown or text incident report.

    Args:
        session_id: Existing NoRepeat session ID.
        filename: Optional incident filename.

    Returns:
        str: Incident report content.
    """
    incident_path = get_incident_path(
        session_id=session_id,
        filename=filename,
    )

    try:
        return incident_path.read_text(
            encoding="utf-8-sig"
        )

    except UnicodeDecodeError as exc:
        raise InvalidIncidentFileError(
            "Incident report must use UTF-8 text encoding."
        ) from exc


def remove_incident(
    session_id: str,
    filename: str,
) -> bool:
    """
    Remove an incident report from a session.

    Args:
        session_id: Existing NoRepeat session ID.
        filename: Incident filename.

    Returns:
        bool: True if the incident was removed.
    """
    incident_path = get_incident_path(
        session_id=session_id,
        filename=filename,
    )

    incident_path.unlink()

    return True