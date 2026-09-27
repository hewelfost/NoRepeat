from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.repository_manager import PROJECT_ROOT, WORKSPACES_DIR


EVIDENCE_DIR = PROJECT_ROOT / "data" / "evidence"
GUARDS_DIR = PROJECT_ROOT / "data" / "guards"
INCIDENTS_DIR = PROJECT_ROOT / "data" / "incidents"
MEMORY_ARCHIVE_DIR = GUARDS_DIR / "incident_memory_archive"

# These paths are project-level Bob assets or source assets and are never
# removed by runtime cleanup.
PROTECTED_TOP_LEVEL_NAMES = {
    ".bob",
    ".git",
    ".venv",
    "venv",
    "bob_sessions",
    "data",
}


class CleanupManagerError(Exception):
    """Raised when generated runtime data cannot be cleaned safely."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_remove_file(path: Path) -> bool:
    if not path.exists() or not path.is_file():
        return False
    path.unlink()
    return True


def _safe_remove_directory(path: Path) -> bool:
    if not path.exists() or not path.is_dir():
        return False
    shutil.rmtree(path)
    return True


def _archive_incident_memories() -> list[dict[str, Any]]:
    """
    Preserve Bob-derived incident memories before workspaces are reset.

    Runtime sessions are disposable, but learned incident memory is valuable.
    Each valid workspace memory is copied into data/guards so cleanup never
    destroys the lesson Bob already extracted from a postmortem.
    """
    archived: list[dict[str, Any]] = []

    if not WORKSPACES_DIR.exists():
        return archived

    MEMORY_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    for workspace in sorted(WORKSPACES_DIR.iterdir()):
        if not workspace.is_dir():
            continue

        memory_path = workspace / "memory" / "incident_memory.json"
        if not memory_path.exists() or not memory_path.is_file():
            continue

        try:
            memory_data = json.loads(memory_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            # Invalid runtime files should not block a cleanup. They are not
            # archived because they cannot be trusted as durable memory.
            continue

        incident_id = None
        if isinstance(memory_data, dict):
            memory_payload = memory_data.get("memory")
            if isinstance(memory_payload, dict):
                value = memory_payload.get("incident_id")
                if isinstance(value, str) and value.strip():
                    incident_id = value.strip()

        safe_incident_id = "".join(
            char if char.isalnum() or char in {"-", "_"} else "-"
            for char in (incident_id or "incident")
        ).strip("-_") or "incident"

        archive_path = (
            MEMORY_ARCHIVE_DIR
            / f"{safe_incident_id}-{workspace.name}.json"
        )

        archive_envelope = {
            "archived_at": _utc_now(),
            "source_session_id": workspace.name,
            "source_path": str(memory_path.resolve()),
            "incident_memory": memory_data,
        }
        archive_path.write_text(
            json.dumps(archive_envelope, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        archived.append(
            {
                "session_id": workspace.name,
                "incident_id": incident_id,
                "archive_path": str(archive_path.resolve()),
            }
        )

    return archived


def remove_session_evidence(session_id: str) -> int:
    """Remove generated evidence files belonging to one session."""
    if not EVIDENCE_DIR.exists():
        return 0

    removed = 0
    for path in EVIDENCE_DIR.glob(f"{session_id}-*.json"):
        if _safe_remove_file(path):
            removed += 1
    return removed


def _clean_runtime_caches() -> dict[str, int]:
    """Remove Python/pytest/temp caches outside protected tool environments."""
    removed_dirs = 0
    removed_files = 0

    protected_roots = {
        (PROJECT_ROOT / ".git").resolve(),
        (PROJECT_ROOT / ".venv").resolve(),
        (PROJECT_ROOT / "venv").resolve(),
        (PROJECT_ROOT / ".bob").resolve(),
        (PROJECT_ROOT / "bob_sessions").resolve(),
        GUARDS_DIR.resolve(),
        INCIDENTS_DIR.resolve(),
    }

    def is_protected(path: Path) -> bool:
        resolved = path.resolve()
        for root in protected_roots:
            try:
                resolved.relative_to(root)
                return True
            except ValueError:
                continue
        return False

    # Remove directories first. Using a materialized list avoids walking into a
    # directory after it has already been deleted.
    cache_dirs = [
        path
        for path in PROJECT_ROOT.rglob("*")
        if path.is_dir()
        and path.name in {"__pycache__", ".pytest_cache"}
        and not is_protected(path)
    ]
    for path in sorted(cache_dirs, key=lambda p: len(p.parts), reverse=True):
        if _safe_remove_directory(path):
            removed_dirs += 1

    temporary_patterns = ("*.pyc", "*.pyo", "*.tmp", "*.temp")
    for pattern in temporary_patterns:
        for path in PROJECT_ROOT.rglob(pattern):
            if path.is_file() and not is_protected(path):
                if _safe_remove_file(path):
                    removed_files += 1

    return {
        "cache_directories_removed": removed_dirs,
        "temporary_files_removed": removed_files,
    }


def cleanup_generated_runtime_data() -> dict[str, Any]:
    """
    Reset generated NoRepeat runtime state while preserving Bob assets.

    Preserved by design:
      - .bob/ custom modes, rules and skills
      - AGENTS.md
      - bob_sessions/ evidence screenshots
      - data/guards/ durable Bob memories
      - data/incidents/ source/demo postmortems
      - source code, .git and local virtual environments

    Removed:
      - all workspaces/sessions and cloned candidate repositories
      - generated data/evidence JSON files
      - Python/pytest/temp caches outside protected environments

    Before sessions are removed, valid incident memories are archived under
    data/guards/incident_memory_archive/.
    """
    archived_memories = _archive_incident_memories()

    workspaces_removed = 0
    if WORKSPACES_DIR.exists():
        for child in list(WORKSPACES_DIR.iterdir()):
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=False)
                workspaces_removed += 1
            elif child.is_file():
                child.unlink()

    WORKSPACES_DIR.mkdir(parents=True, exist_ok=True)

    evidence_removed = 0
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    for path in EVIDENCE_DIR.iterdir():
        if path.name == ".gitkeep":
            continue
        if path.is_dir():
            shutil.rmtree(path)
            evidence_removed += 1
        elif path.is_file():
            path.unlink()
            evidence_removed += 1

    cache_report = _clean_runtime_caches()

    return {
        "success": True,
        "cleaned_at": _utc_now(),
        "workspaces_removed": workspaces_removed,
        "evidence_entries_removed": evidence_removed,
        "archived_incident_memories": archived_memories,
        **cache_report,
        "preserved": [
            ".bob/",
            "AGENTS.md",
            "bob_sessions/",
            "data/guards/",
            "data/incidents/",
            ".git/",
            ".venv/ and venv/",
        ],
    }
