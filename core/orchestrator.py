from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.incident_manager import (
    get_incident_path,
    get_session_workspace,
    import_incident_file,
    save_uploaded_incident,
)
from core.repository_manager import (
    clone_github_repository,
    extract_zip_repository,
    remove_session_workspace,
)
from core.replay_engine import (
    run_full_test_suite,
    run_incident_replay,
)


SESSION_MANIFEST_NAME = "norepeat_session.json"


class OrchestratorError(Exception):
    """Base exception for NoRepeat orchestration errors."""


class InvalidSessionStateError(OrchestratorError):
    """Raised when an operation is not valid for the current session state."""


def _utc_now() -> str:
    """Return the current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


def _manifest_path(session_id: str) -> Path:
    """
    Return the session manifest path.

    Structure:
        workspaces/<session_id>/norepeat_session.json
    """
    workspace = get_session_workspace(session_id)
    return workspace / SESSION_MANIFEST_NAME


def _save_manifest(
    session_id: str,
    manifest: dict[str, Any],
) -> None:
    """Persist session metadata inside the session workspace."""
    manifest["updated_at"] = _utc_now()

    path = _manifest_path(session_id)

    with path.open("w", encoding="utf-8") as file:
        json.dump(
            manifest,
            file,
            indent=2,
            ensure_ascii=False,
        )


def load_session_manifest(
    session_id: str,
) -> dict[str, Any]:
    """
    Load a NoRepeat session manifest.

    Args:
        session_id: Existing NoRepeat session identifier.

    Returns:
        dict: Session metadata.
    """
    path = _manifest_path(session_id)

    if not path.exists():
        raise OrchestratorError(
            f"No NoRepeat manifest exists for session '{session_id}'."
        )

    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)

    except json.JSONDecodeError as exc:
        raise OrchestratorError(
            f"Session manifest for '{session_id}' is invalid."
        ) from exc


def _create_manifest(
    repository_metadata: dict[str, Any],
) -> dict[str, Any]:
    """Create the initial NoRepeat session manifest."""
    session_id = repository_metadata["session_id"]

    manifest: dict[str, Any] = {
        "session_id": session_id,
        "status": "REPOSITORY_READY",
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
        "repository": {
            "source_type": repository_metadata.get("source_type"),
            "source": repository_metadata.get("source"),
            "repository_path": repository_metadata.get("repository_path"),
            "commit_sha": repository_metadata.get("commit_sha"),
        },
        "incident": None,
        "baseline": None,
        "replay": None,
        "verification": None,
        "proof": {
            "status": "PENDING",
        },
    }

    _save_manifest(
        session_id=session_id,
        manifest=manifest,
    )

    return manifest


def create_session_from_github(
    repository_url: str,
) -> dict[str, Any]:
    """
    Start a NoRepeat session using a public GitHub repository.

    Flow:
        GitHub URL
            ↓
        Clone repository
            ↓
        Create session manifest
    """
    repository_metadata = clone_github_repository(
        repository_url
    )

    return _create_manifest(
        repository_metadata
    )


def create_session_from_zip(
    zip_path: str | Path,
) -> dict[str, Any]:
    """
    Start a NoRepeat session using a ZIP project.
    """
    repository_metadata = extract_zip_repository(
        zip_path
    )

    return _create_manifest(
        repository_metadata
    )


def attach_local_incident(
    session_id: str,
    incident_path: str | Path,
) -> dict[str, Any]:
    """
    Attach a local Markdown/text incident report to a NoRepeat session.

    This is useful during development and for the controlled hackathon demo.
    """
    incident_metadata = import_incident_file(
        session_id=session_id,
        source_path=incident_path,
    )

    manifest = load_session_manifest(
        session_id
    )

    manifest["incident"] = incident_metadata
    manifest["status"] = "READY_FOR_ANALYSIS"

    _save_manifest(
        session_id=session_id,
        manifest=manifest,
    )

    return manifest


def attach_uploaded_incident(
    session_id: str,
    filename: str,
    content: bytes,
) -> dict[str, Any]:
    """
    Attach an uploaded incident report to a NoRepeat session.

    This method will later be used by the Flask API and Streamlit frontend.
    """
    incident_metadata = save_uploaded_incident(
        session_id=session_id,
        filename=filename,
        content=content,
    )

    manifest = load_session_manifest(
        session_id
    )

    manifest["incident"] = incident_metadata
    manifest["status"] = "READY_FOR_ANALYSIS"

    _save_manifest(
        session_id=session_id,
        manifest=manifest,
    )

    return manifest


def _require_incident(
    manifest: dict[str, Any],
) -> None:
    """Ensure that a session contains an incident report."""
    if not manifest.get("incident"):
        raise InvalidSessionStateError(
            "The session does not contain an incident report."
        )


def run_baseline(
    session_id: str,
) -> dict[str, Any]:
    """
    Run the project's existing tests before NoRepeat generates
    the incident regression test.

    Desired hackathon result:
        Existing tests → PASS

    This demonstrates that the project appears healthy before
    NoRepeat applies historical incident knowledge.
    """
    manifest = load_session_manifest(
        session_id
    )

    _require_incident(manifest)

    result = run_full_test_suite(
        session_id=session_id,
        evidence_label="baseline",
    )

    manifest["baseline"] = result

    if result["success"]:
        manifest["status"] = "BASELINE_PASSED"
    else:
        manifest["status"] = "BASELINE_FAILED"

    _save_manifest(
        session_id=session_id,
        manifest=manifest,
    )

    return result


def replay_incident(
    session_id: str,
    incident_test_path: str,
) -> dict[str, Any]:
    """
    Execute the regression test generated for the historical incident.

    Expected BEFORE the fix:
        Regression test → FAIL

    A failing regression test means the historical incident condition
    has been successfully reproduced.
    """
    manifest = load_session_manifest(
        session_id
    )

    _require_incident(manifest)

    result = run_incident_replay(
        session_id=session_id,
        incident_test_path=incident_test_path,
        evidence_label="before-fix",
    )

    replay_data = {
        "test_path": incident_test_path,
        "pytest": result,
        "incident_reproduced": not result["success"],
    }

    manifest["replay"] = replay_data

    if replay_data["incident_reproduced"]:
        manifest["status"] = "INCIDENT_REPRODUCED"
    else:
        manifest["status"] = "INCIDENT_NOT_REPRODUCED"

    _save_manifest(
        session_id=session_id,
        manifest=manifest,
    )

    return replay_data


def verify_after_fix(
    session_id: str,
    incident_test_path: str,
) -> dict[str, Any]:
    """
    Re-run the incident regression test and full project test suite
    after Bob applies a remediation.

    Verification requires:
        1. Incident regression test passes.
        2. Existing project test suite passes.

    Only when both conditions are true is non-recurrence considered
    verified for the known incident scenario.
    """
    manifest = load_session_manifest(
        session_id
    )

    _require_incident(manifest)

    if not manifest.get("replay"):
        raise InvalidSessionStateError(
            "The incident must be replayed before fix verification."
        )

    incident_result = run_incident_replay(
        session_id=session_id,
        incident_test_path=incident_test_path,
        evidence_label="after-fix-incident",
    )

    full_suite_result = run_full_test_suite(
        session_id=session_id,
        evidence_label="after-fix-full-suite",
    )

    verified = (
        incident_result["success"]
        and full_suite_result["success"]
    )

    verification = {
        "incident_test": incident_result,
        "full_test_suite": full_suite_result,
        "verified": verified,
    }

    manifest["verification"] = verification

    if verified:
        manifest["status"] = "NON_RECURRENCE_VERIFIED"
        manifest["proof"] = {
            "status": "VERIFIED",
            "verified_at": _utc_now(),
        }
    else:
        manifest["status"] = "VERIFICATION_FAILED"
        manifest["proof"] = {
            "status": "FAILED",
            "verified_at": None,
        }

    _save_manifest(
        session_id=session_id,
        manifest=manifest,
    )

    return verification


def generate_proof_of_non_recurrence(
    session_id: str,
) -> dict[str, Any]:
    """
    Build the final structured Proof of Non-Recurrence.

    This does not claim that the application is universally secure.
    It proves only that the known incident scenario represented by
    the generated regression test no longer reproduces successfully.
    """
    manifest = load_session_manifest(
        session_id
    )

    _require_incident(manifest)

    replay = manifest.get("replay")
    verification = manifest.get("verification")

    if not replay:
        raise InvalidSessionStateError(
            "Incident replay evidence is missing."
        )

    if not verification:
        raise InvalidSessionStateError(
            "Post-fix verification evidence is missing."
        )

    repository = manifest["repository"]
    incident = manifest["incident"]

    proof = {
        "proof_type": "NoRepeat Proof of Non-Recurrence",
        "session_id": session_id,
        "generated_at": _utc_now(),
        "repository": {
            "source": repository.get("source"),
            "source_type": repository.get("source_type"),
            "commit_sha": repository.get("commit_sha"),
        },
        "incident": {
            "filename": incident.get("filename"),
            "sha256": incident.get("sha256"),
        },
        "original_replay": {
            "incident_reproduced": replay.get(
                "incident_reproduced"
            ),
            "test_path": replay.get("test_path"),
        },
        "verification": {
            "incident_test_passed": verification[
                "incident_test"
            ]["success"],
            "full_test_suite_passed": verification[
                "full_test_suite"
            ]["success"],
        },
        "non_recurrence_verified": verification[
            "verified"
        ],
        "scope": (
            "This proof verifies that the known incident scenario "
            "represented by the regression test no longer reproduces. "
            "It is not a guarantee that the application contains no "
            "other vulnerabilities."
        ),
    }

    workspace = get_session_workspace(
        session_id
    )

    proof_path = (
        workspace
        / "proof_of_non_recurrence.json"
    )

    with proof_path.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            proof,
            file,
            indent=2,
            ensure_ascii=False,
        )

    manifest["proof"] = {
        "status": (
            "VERIFIED"
            if proof["non_recurrence_verified"]
            else "FAILED"
        ),
        "path": str(proof_path.resolve()),
        "generated_at": proof["generated_at"],
    }

    _save_manifest(
        session_id=session_id,
        manifest=manifest,
    )

    return proof


def get_session_status(
    session_id: str,
) -> dict[str, Any]:
    """
    Return a simplified session status for the API/dashboard.
    """
    manifest = load_session_manifest(
        session_id
    )

    return {
        "session_id": session_id,
        "status": manifest.get("status"),
        "repository": manifest.get("repository"),
        "incident": manifest.get("incident"),
        "baseline_completed": (
            manifest.get("baseline") is not None
        ),
        "incident_replay_completed": (
            manifest.get("replay") is not None
        ),
        "verification_completed": (
            manifest.get("verification") is not None
        ),
        "proof": manifest.get("proof"),
    }


def delete_session(
    session_id: str,
) -> bool:
    """
    Delete an entire NoRepeat analysis workspace.
    """
    return remove_session_workspace(
        session_id
    )