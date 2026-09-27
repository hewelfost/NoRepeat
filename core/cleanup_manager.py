from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.repository_manager import PROJECT_ROOT, WORKSPACES_DIR


EVIDENCE_DIR = PROJECT_ROOT / "data" / "evidence"
GUARDS_DIR = PROJECT_ROOT / "data" / "guards"
INCIDENTS_DIR = PROJECT_ROOT / "data" / "incidents"


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


def remove_session_evidence(session_id: str) -> int:
    """Remove generated evidence files belonging to one session."""
    if not EVIDENCE_DIR.exists():
        return 0

    removed = 0
    for path in EVIDENCE_DIR.glob(f"{session_id}-*.json"):
        if _safe_remove_file(path):
            removed += 1
    return removed


def _clear_directory_except_gitkeep(directory: Path) -> int:
    """Remove every generated entry in a runtime directory except .gitkeep."""
    directory.mkdir(parents=True, exist_ok=True)
    removed = 0

    for child in list(directory.iterdir()):
        if child.name == ".gitkeep":
            continue

        if child.is_dir():
            shutil.rmtree(child)
            removed += 1
        elif child.is_file():
            child.unlink()
            removed += 1

    return removed


def _clean_runtime_caches() -> dict[str, int]:
    """Remove Python/pytest/temp caches without touching Bob or source assets."""
    removed_dirs = 0
    removed_files = 0

    protected_roots = {
        (PROJECT_ROOT / ".git").resolve(),
        (PROJECT_ROOT / ".venv").resolve(),
        (PROJECT_ROOT / "venv").resolve(),
        (PROJECT_ROOT / ".bob").resolve(),
        (PROJECT_ROOT / "bob_sessions").resolve(),
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

    for pattern in ("*.pyc", "*.pyo", "*.tmp", "*.temp"):
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
    Return NoRepeat to a clean runtime state.

    This is intentionally a *hard runtime reset*. It removes every generated
    session artifact that can contaminate a later run, while preserving the
    files that define NoRepeat and IBM Bob's project configuration.

    Preserved:
      - .bob/ custom mode, rules and skill
      - AGENTS.md
      - bob_sessions/ development/hackathon evidence
      - data/incidents/ predefined/source incident documents
      - source code, .git and local virtual environments

    Removed:
      - every active workspace/session and cloned candidate repository
      - uploaded postmortems copied into session workspaces
      - generated Incident Memory, recurrence analysis, guards, replay,
        remediation, verification and proof artifacts inside workspaces
      - data/evidence runtime JSON
      - generated data/guards entries (for example archived Incident Memory)
      - Python/pytest/temp caches outside protected environments

    Keeping Incident Memory inside a deleted session would defeat a hard reset,
    so runtime memories are deleted with their session. Bob's persistent project
    behavior remains preserved in .bob/ and AGENTS.md.
    """
    workspaces_removed = 0
    workspace_entries_removed = 0

    WORKSPACES_DIR.mkdir(parents=True, exist_ok=True)
    for child in list(WORKSPACES_DIR.iterdir()):
        if child.is_dir():
            shutil.rmtree(child)
            workspaces_removed += 1
        elif child.is_file():
            child.unlink()
            workspace_entries_removed += 1

    evidence_removed = _clear_directory_except_gitkeep(EVIDENCE_DIR)
    generated_guards_removed = _clear_directory_except_gitkeep(GUARDS_DIR)
    cache_report = _clean_runtime_caches()

    return {
        "success": True,
        "cleaned_at": _utc_now(),
        "workspaces_removed": workspaces_removed,
        "workspace_files_removed": workspace_entries_removed,
        "evidence_entries_removed": evidence_removed,
        "generated_guard_entries_removed": generated_guards_removed,
        **cache_report,
        "preserved": [
            ".bob/",
            "AGENTS.md",
            "bob_sessions/",
            "data/incidents/",
            ".git/",
            ".venv/ and venv/",
            "source code",
        ],
    }
