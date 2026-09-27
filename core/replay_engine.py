from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from core.repository_manager import get_session_repository_path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
EVIDENCE_DIR = PROJECT_ROOT / "data" / "evidence"
DEFAULT_TIMEOUT_SECONDS = 120


class ReplayEngineError(Exception):
    """Base exception for NoRepeat replay errors."""


class RepositoryNotFoundError(ReplayEngineError):
    """Raised when a session does not contain a repository."""


class InvalidTestTargetError(ReplayEngineError):
    """Raised when a requested test target is invalid."""


class ReplayTimeoutError(ReplayEngineError):
    """Raised when pytest exceeds the configured timeout."""


def _ensure_evidence_directory() -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)


def get_repository_path(session_id: str) -> Path:
    """Return the normalized repository root for a NoRepeat session."""
    try:
        repository_path = get_session_repository_path(session_id)
    except Exception as exc:
        raise RepositoryNotFoundError(
            f"No repository exists for session '{session_id}'."
        ) from exc

    if not repository_path.exists() or not repository_path.is_dir():
        raise RepositoryNotFoundError(
            f"Repository path for session '{session_id}' is invalid."
        )

    return repository_path


def _validate_test_target(
    repository_path: Path,
    test_target: str | None,
) -> str | None:
    if test_target is None:
        return None

    test_target = test_target.strip()

    if not test_target:
        return None

    target_path = (repository_path / test_target).resolve()

    try:
        target_path.relative_to(repository_path)
    except ValueError as exc:
        raise InvalidTestTargetError(
            "Test target must remain inside the analyzed repository."
        ) from exc

    if not target_path.exists():
        raise InvalidTestTargetError(
            f"Test target does not exist: {test_target}"
        )

    return str(target_path)


def _parse_pytest_summary(output: str) -> dict:
    counters = {
        "passed": 0,
        "failed": 0,
        "errors": 0,
        "skipped": 0,
        "xfailed": 0,
        "xpassed": 0,
    }

    patterns = {
        "passed": r"(\d+)\s+passed",
        "failed": r"(\d+)\s+failed",
        "errors": r"(\d+)\s+errors?",
        "skipped": r"(\d+)\s+skipped",
        "xfailed": r"(\d+)\s+xfailed",
        "xpassed": r"(\d+)\s+xpassed",
    }

    for key, pattern in patterns.items():
        matches = re.findall(pattern, output, flags=re.IGNORECASE)
        if matches:
            counters[key] = int(matches[-1])

    return counters


def _pytest_exit_status(return_code: int) -> str:
    statuses = {
        0: "PASS",
        1: "FAIL",
        2: "INTERRUPTED",
        3: "PYTEST_ERROR",
        4: "USAGE_ERROR",
        5: "NO_TESTS_COLLECTED",
    }
    return statuses.get(return_code, "UNKNOWN_ERROR")


def _sanitize_evidence_label(label: str) -> str:
    safe_label = re.sub(
        r"[^A-Za-z0-9_-]+",
        "-",
        label.strip(),
    ).strip("-_")

    if not safe_label:
        raise ReplayEngineError(
            "Evidence label cannot be empty."
        )

    return safe_label


def save_replay_evidence(
    result: dict,
    evidence_label: str,
) -> Path:
    """Persist structured pytest evidence under data/evidence/."""
    _ensure_evidence_directory()
    safe_label = _sanitize_evidence_label(evidence_label)
    session_id = result.get("session_id")

    if not session_id:
        raise ReplayEngineError(
            "Replay result does not contain a session ID."
        )

    evidence_path = EVIDENCE_DIR / f"{session_id}-{safe_label}.json"
    evidence_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return evidence_path.resolve()


def run_pytest(
    session_id: str,
    test_target: str | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    evidence_label: str | None = None,
    extra_args: list[str] | None = None,
) -> dict:
    """
    Execute pytest inside the session repository and capture evidence.

    NoRepeat should execute only trusted/controlled demo repositories until
    the runner is isolated in a proper sandbox or container boundary.
    """
    if timeout_seconds <= 0:
        raise ReplayEngineError(
            "Timeout must be greater than zero."
        )

    repository_path = get_repository_path(session_id)
    validated_target = _validate_test_target(
        repository_path,
        test_target,
    )

    command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
    ]

    if extra_args:
        command.extend(extra_args)

    if validated_target:
        command.append(validated_target)

    started_at = datetime.now(timezone.utc).isoformat()
    start_time = time.perf_counter()

    try:
        process = subprocess.run(
            command,
            cwd=str(repository_path),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        duration_seconds = round(
            time.perf_counter() - start_time,
            3,
        )
        raise ReplayTimeoutError(
            f"pytest exceeded the {timeout_seconds}-second timeout "
            f"after {duration_seconds} seconds."
        ) from exc

    duration_seconds = round(
        time.perf_counter() - start_time,
        3,
    )

    stdout = process.stdout or ""
    stderr = process.stderr or ""
    combined_output = "\n".join(
        part for part in [stdout, stderr] if part.strip()
    )

    counters = _parse_pytest_summary(combined_output)
    status = _pytest_exit_status(process.returncode)

    result = {
        "success": process.returncode == 0,
        "session_id": session_id,
        "status": status,
        "return_code": process.returncode,
        "repository_path": str(repository_path),
        "test_target": test_target,
        "command": command,
        "started_at": started_at,
        "duration_seconds": duration_seconds,
        "results": counters,
        "stdout": stdout,
        "stderr": stderr,
    }

    if evidence_label:
        evidence_path = save_replay_evidence(
            result,
            evidence_label,
        )
        result["evidence_path"] = str(evidence_path)

    return result


def run_full_test_suite(
    session_id: str,
    evidence_label: str | None = None,
) -> dict:
    return run_pytest(
        session_id=session_id,
        evidence_label=evidence_label,
    )


def run_incident_replay(
    session_id: str,
    incident_test_path: str,
    evidence_label: str = "incident-replay",
) -> dict:
    return run_pytest(
        session_id=session_id,
        test_target=incident_test_path,
        evidence_label=evidence_label,
    )
