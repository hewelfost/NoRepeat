from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.repository_manager import WORKSPACES_DIR


ALLOWED_INCIDENT_EXTENSIONS = {".md", ".txt"}
MAX_INCIDENT_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB
INCIDENT_MEMORY_FILENAME = "incident_memory.json"


class IncidentManagerError(Exception):
    """Base exception for incident management errors."""


class InvalidIncidentFileError(IncidentManagerError):
    """Raised when an incident file is invalid or unsupported."""


class InvalidIncidentMemoryError(IncidentManagerError):
    """Raised when a structured incident memory is invalid."""


class SessionNotFoundError(IncidentManagerError):
    """Raised when a NoRepeat session workspace does not exist."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate_session_id(session_id: str) -> str:
    session_id = session_id.strip()

    if not session_id:
        raise IncidentManagerError("Session ID cannot be empty.")

    if not session_id.replace("-", "").replace("_", "").isalnum():
        raise IncidentManagerError("Invalid session ID.")

    return session_id


def get_session_workspace(session_id: str) -> Path:
    """Return the workspace path for an existing NoRepeat session."""
    session_id = _validate_session_id(session_id)
    workspace_path = (WORKSPACES_DIR / session_id).resolve()
    workspaces_root = WORKSPACES_DIR.resolve()

    try:
        workspace_path.relative_to(workspaces_root)
    except ValueError as exc:
        raise IncidentManagerError(
            "Session workspace resolved outside the allowed directory."
        ) from exc

    if not workspace_path.exists() or not workspace_path.is_dir():
        raise SessionNotFoundError(
            f"No workspace exists for session '{session_id}'."
        )

    return workspace_path


def _sanitize_filename(filename: str) -> str:
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
    sha256 = hashlib.sha256()

    with file_path.open("rb") as file:
        for chunk in iter(lambda: file.read(8192), b""):
            sha256.update(chunk)

    return sha256.hexdigest()


def _get_incident_directory(session_id: str) -> Path:
    workspace_path = get_session_workspace(session_id)
    incident_directory = workspace_path / "incident"
    incident_directory.mkdir(parents=True, exist_ok=True)
    return incident_directory


def _get_memory_directory(session_id: str) -> Path:
    workspace_path = get_session_workspace(session_id)
    memory_directory = workspace_path / "memory"
    memory_directory.mkdir(parents=True, exist_ok=True)
    return memory_directory


def save_uploaded_incident(
    session_id: str,
    filename: str,
    content: bytes,
    overwrite: bool = False,
) -> dict:
    """Save a user-uploaded historical postmortem in the session."""
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
        "source": "user_upload",
    }


def import_incident_file(
    session_id: str,
    source_path: str | Path,
    overwrite: bool = False,
) -> dict:
    """Import a local postmortem for development or controlled demos."""
    source = Path(source_path).resolve()

    if not source.exists() or not source.is_file():
        raise InvalidIncidentFileError(
            f"Incident file does not exist or is not a file: {source}"
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
        "source": "local_import",
    }


def list_incidents(session_id: str) -> list[dict]:
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
    incident_path = get_incident_path(
        session_id=session_id,
        filename=filename,
    )

    try:
        return incident_path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise InvalidIncidentFileError(
            "Incident report must use UTF-8 text encoding."
        ) from exc


def save_incident_memory(
    session_id: str,
    memory: dict[str, Any],
    *,
    source_incident_sha256: str | None = None,
    overwrite: bool = True,
) -> dict[str, Any]:
    """
    Persist Bob's future structured understanding of the user postmortem.

    This function does not analyze the postmortem itself. It only provides
    durable application memory once Bob produces the structured result.
    """
    if not isinstance(memory, dict) or not memory:
        raise InvalidIncidentMemoryError(
            "Incident memory must be a non-empty JSON object."
        )

    try:
        json.dumps(memory, ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise InvalidIncidentMemoryError(
            "Incident memory must contain JSON-serializable values."
        ) from exc

    memory_directory = _get_memory_directory(session_id)
    memory_path = memory_directory / INCIDENT_MEMORY_FILENAME

    if memory_path.exists() and not overwrite:
        raise InvalidIncidentMemoryError(
            "Incident memory already exists for this session."
        )

    envelope = {
        "schema_version": 1,
        "session_id": session_id,
        "saved_at": _utc_now(),
        "source_incident_sha256": source_incident_sha256,
        "memory": memory,
    }

    memory_path.write_text(
        json.dumps(envelope, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return {
        "success": True,
        "memory_path": str(memory_path.resolve()),
        **envelope,
    }


def load_incident_memory(session_id: str) -> dict[str, Any] | None:
    """Load the persisted structured incident memory, if it exists."""
    memory_path = _get_memory_directory(session_id) / INCIDENT_MEMORY_FILENAME

    if not memory_path.exists():
        return None

    try:
        data = json.loads(memory_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise InvalidIncidentMemoryError(
            "Stored incident memory is invalid JSON."
        ) from exc

    if not isinstance(data, dict):
        raise InvalidIncidentMemoryError(
            "Stored incident memory has an invalid structure."
        )

    return data


def remove_incident_memory(session_id: str) -> bool:
    """Remove persisted incident memory for a session."""
    memory_path = _get_memory_directory(session_id) / INCIDENT_MEMORY_FILENAME

    if not memory_path.exists():
        return False

    memory_path.unlink()
    return True


def remove_incident(
    session_id: str,
    filename: str,
) -> bool:
    """Remove a historical postmortem and its derived incident memory."""
    incident_path = get_incident_path(
        session_id=session_id,
        filename=filename,
    )
    incident_path.unlink()
    remove_incident_memory(session_id)
    return True
