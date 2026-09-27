from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.incident_manager import (
    get_session_workspace,
    import_incident_file,
    load_incident_memory,
    save_incident_memory,
    save_uploaded_incident,
)
from core.repository_manager import (
    PROJECT_ROOT,
    clone_github_repository,
    extract_zip_repository,
    remove_session_workspace,
    switch_session_revision,
)
from core.replay_engine import (
    run_full_test_suite,
    run_incident_replay,
)


SESSION_MANIFEST_NAME = "norepeat_session.json"
EVIDENCE_DIR = PROJECT_ROOT / "data" / "evidence"


class OrchestratorError(Exception):
    """Base exception for NoRepeat orchestration errors."""


class InvalidSessionStateError(OrchestratorError):
    """Raised when an operation is not valid for the current session state."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _manifest_path(session_id: str) -> Path:
    workspace = get_session_workspace(session_id)
    return workspace / SESSION_MANIFEST_NAME


def _save_manifest(
    session_id: str,
    manifest: dict[str, Any],
) -> None:
    manifest["updated_at"] = _utc_now()
    path = _manifest_path(session_id)
    path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def load_session_manifest(
    session_id: str,
) -> dict[str, Any]:
    path = _manifest_path(session_id)

    if not path.exists():
        raise OrchestratorError(
            f"No NoRepeat manifest exists for session '{session_id}'."
        )

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise OrchestratorError(
            f"Session manifest for '{session_id}' is invalid."
        ) from exc

    if not isinstance(data, dict):
        raise OrchestratorError(
            f"Session manifest for '{session_id}' has an invalid structure."
        )

    return data


def _repository_manifest(
    repository_metadata: dict[str, Any],
) -> dict[str, Any]:
    return {
        "source_type": repository_metadata.get("source_type"),
        "source": repository_metadata.get("source"),
        "repository_path": repository_metadata.get("repository_path"),
        "requested_revision": repository_metadata.get("requested_revision"),
        "resolved_revision": repository_metadata.get("resolved_revision"),
        "commit_sha": repository_metadata.get("commit_sha"),
        "default_branch": repository_metadata.get("default_branch"),
        "supports_revision_switching": repository_metadata.get(
            "supports_revision_switching",
            False,
        ),
    }


def _create_manifest(
    repository_metadata: dict[str, Any],
) -> dict[str, Any]:
    session_id = repository_metadata["session_id"]

    manifest: dict[str, Any] = {
        "schema_version": 2,
        "session_id": session_id,
        "status": "REPOSITORY_READY",
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
        "repository": _repository_manifest(repository_metadata),
        "incident": None,
        "incident_memory": None,
        "baseline": None,
        "recurrence_analysis": None,
        "replay": None,
        "verification": None,
        "proof": {
            "status": "PENDING",
        },
    }

    _save_manifest(session_id, manifest)
    return manifest


def create_session_from_github(
    repository_url: str,
    revision: str | None = None,
) -> dict[str, Any]:
    repository_metadata = clone_github_repository(
        repository_url=repository_url,
        revision=revision,
    )
    return _create_manifest(repository_metadata)


def create_session_from_zip(
    zip_path: str | Path,
) -> dict[str, Any]:
    repository_metadata = extract_zip_repository(zip_path)
    return _create_manifest(repository_metadata)


def _clear_candidate_results(
    manifest: dict[str, Any],
) -> None:
    """
    Clear results tied to the current code revision.

    Incident memory is intentionally preserved because it represents the
    historical lesson learned from the user's postmortem, not a property of
    the candidate revision being audited.
    """
    manifest["baseline"] = None
    manifest["recurrence_analysis"] = None
    manifest["replay"] = None
    manifest["verification"] = None
    manifest["proof"] = {"status": "PENDING"}


def _clear_incident_derived_results(
    manifest: dict[str, Any],
) -> None:
    """Clear everything derived from the historical incident."""
    manifest["incident_memory"] = None
    _clear_candidate_results(manifest)


def _status_after_candidate_reset(
    manifest: dict[str, Any],
) -> str:
    if manifest.get("incident_memory"):
        return "INCIDENT_MEMORY_READY"
    if manifest.get("incident"):
        return "HISTORICAL_INCIDENT_ATTACHED"
    return "REPOSITORY_READY"


def set_candidate_revision(
    session_id: str,
    revision: str,
) -> dict[str, Any]:
    """Switch the candidate revision while preserving historical memory."""
    manifest = load_session_manifest(session_id)
    repository = manifest.get("repository") or {}

    if repository.get("source_type") != "github":
        raise InvalidSessionStateError(
            "Revision switching is only available for GitHub sessions."
        )

    revision_metadata = switch_session_revision(
        session_id=session_id,
        revision=revision,
    )

    repository["requested_revision"] = revision_metadata.get(
        "requested_revision"
    )
    repository["resolved_revision"] = revision_metadata.get(
        "resolved_revision"
    )
    repository["commit_sha"] = revision_metadata.get("commit_sha")
    manifest["repository"] = repository

    _clear_candidate_results(manifest)
    manifest["status"] = _status_after_candidate_reset(manifest)
    _save_manifest(session_id, manifest)
    return manifest


def attach_local_incident(
    session_id: str,
    incident_path: str | Path,
) -> dict[str, Any]:
    manifest = load_session_manifest(session_id)

    if manifest.get("incident"):
        raise InvalidSessionStateError(
            "This session already contains a historical incident report. "
            "Create a new session to audit a different postmortem."
        )

    incident_metadata = import_incident_file(
        session_id=session_id,
        source_path=incident_path,
    )

    manifest["incident"] = incident_metadata
    _clear_incident_derived_results(manifest)
    manifest["status"] = "HISTORICAL_INCIDENT_ATTACHED"
    _save_manifest(session_id, manifest)
    return manifest


def attach_uploaded_incident(
    session_id: str,
    filename: str,
    content: bytes,
) -> dict[str, Any]:
    """Attach the historical postmortem supplied by the user."""
    manifest = load_session_manifest(session_id)

    if manifest.get("incident"):
        raise InvalidSessionStateError(
            "This session already contains a historical incident report. "
            "Create a new session to audit a different postmortem."
        )

    incident_metadata = save_uploaded_incident(
        session_id=session_id,
        filename=filename,
        content=content,
    )

    manifest["incident"] = incident_metadata
    _clear_incident_derived_results(manifest)
    manifest["status"] = "HISTORICAL_INCIDENT_ATTACHED"
    _save_manifest(session_id, manifest)
    return manifest


def _require_incident(manifest: dict[str, Any]) -> None:
    if not manifest.get("incident"):
        raise InvalidSessionStateError(
            "The user must attach a historical postmortem before continuing."
        )


def _require_incident_memory(manifest: dict[str, Any]) -> None:
    if not manifest.get("incident_memory"):
        raise InvalidSessionStateError(
            "Historical incident memory is not ready. "
            "IBM Bob must analyze the uploaded postmortem first."
        )


def _require_recurrence(manifest: dict[str, Any]) -> dict[str, Any]:
    analysis = manifest.get("recurrence_analysis")

    if not analysis:
        raise InvalidSessionStateError(
            "Historical recurrence analysis has not been completed yet."
        )

    if not analysis.get("detected"):
        raise InvalidSessionStateError(
            "No historical recurrence was detected for this revision, "
            "so there is no recurrence scenario to replay."
        )

    return analysis


def run_baseline(
    session_id: str,
) -> dict[str, Any]:
    """Run existing tests against the candidate revision before Bob changes it."""
    manifest = load_session_manifest(session_id)
    _require_incident(manifest)

    result = run_full_test_suite(
        session_id=session_id,
        evidence_label="baseline",
    )

    result["candidate_commit_sha"] = (
        manifest.get("repository", {}).get("commit_sha")
    )
    manifest["baseline"] = result
    manifest["status"] = (
        "BASELINE_PASSED" if result["success"] else "BASELINE_FAILED"
    )
    _save_manifest(session_id, manifest)
    return result


def record_incident_memory(
    session_id: str,
    memory: dict[str, Any],
) -> dict[str, Any]:
    """
    Persist Bob's structured interpretation of the user-supplied postmortem.

    This is the integration point that bob_runner.py will call later.
    """
    manifest = load_session_manifest(session_id)
    _require_incident(manifest)

    incident = manifest["incident"]
    persisted = save_incident_memory(
        session_id=session_id,
        memory=memory,
        source_incident_sha256=incident.get("sha256"),
        overwrite=True,
    )

    manifest["incident_memory"] = {
        "schema_version": persisted.get("schema_version"),
        "saved_at": persisted.get("saved_at"),
        "source_incident_sha256": persisted.get("source_incident_sha256"),
        "memory_path": persisted.get("memory_path"),
        "memory": persisted.get("memory"),
    }
    manifest["status"] = "INCIDENT_MEMORY_READY"
    _save_manifest(session_id, manifest)
    return manifest


def _save_recurrence_evidence(
    session_id: str,
    analysis: dict[str, Any],
) -> Path:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    path = EVIDENCE_DIR / f"{session_id}-recurrence-analysis.json"
    path.write_text(
        json.dumps(analysis, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return path.resolve()


def record_recurrence_analysis(
    session_id: str,
    analysis: dict[str, Any],
) -> dict[str, Any]:
    """
    Record Bob's semantic comparison between incident memory and candidate code.

    Expected minimum shape:
        {
            "detected": true | false,
            "summary": "...",
            "evidence": [...]
        }
    """
    manifest = load_session_manifest(session_id)
    _require_incident(manifest)
    _require_incident_memory(manifest)

    if manifest.get("baseline") is None:
        raise InvalidSessionStateError(
            "Run the project baseline before recording recurrence analysis."
        )

    if not isinstance(analysis, dict) or not analysis:
        raise OrchestratorError(
            "Recurrence analysis must be a non-empty JSON object."
        )

    detected = analysis.get("detected")
    if not isinstance(detected, bool):
        raise OrchestratorError(
            "Recurrence analysis must include a boolean 'detected' field."
        )

    repository = manifest.get("repository") or {}
    enriched = dict(analysis)
    enriched.update(
        {
            "recorded_at": _utc_now(),
            "candidate_revision": repository.get("requested_revision"),
            "candidate_commit_sha": repository.get("commit_sha"),
            "incident_sha256": manifest["incident"].get("sha256"),
        }
    )

    evidence_path = _save_recurrence_evidence(
        session_id,
        enriched,
    )
    enriched["evidence_path"] = str(evidence_path)

    manifest["recurrence_analysis"] = enriched
    manifest["replay"] = None
    manifest["verification"] = None
    manifest["proof"] = {"status": "PENDING"}
    manifest["status"] = (
        "RECURRENCE_DETECTED"
        if detected
        else "NO_KNOWN_RECURRENCE"
    )
    _save_manifest(session_id, manifest)
    return enriched


def replay_incident(
    session_id: str,
    incident_test_path: str,
) -> dict[str, Any]:
    """Execute Bob's regression test after recurrence has been detected."""
    manifest = load_session_manifest(session_id)
    _require_incident(manifest)
    _require_incident_memory(manifest)
    _require_recurrence(manifest)

    result = run_incident_replay(
        session_id=session_id,
        incident_test_path=incident_test_path,
        evidence_label="before-fix",
    )

    replay_data = {
        "test_path": incident_test_path,
        "pytest": result,
        "incident_reproduced": not result["success"],
        "candidate_commit_sha": (
            manifest.get("repository", {}).get("commit_sha")
        ),
    }

    manifest["replay"] = replay_data
    manifest["status"] = (
        "INCIDENT_REPRODUCED"
        if replay_data["incident_reproduced"]
        else "INCIDENT_NOT_REPRODUCED"
    )
    _save_manifest(session_id, manifest)
    return replay_data


def verify_after_fix(
    session_id: str,
    incident_test_path: str,
) -> dict[str, Any]:
    """Verify the regression test and full suite after Bob remediation."""
    manifest = load_session_manifest(session_id)
    _require_incident(manifest)
    _require_incident_memory(manifest)
    _require_recurrence(manifest)

    replay = manifest.get("replay")
    if not replay or not replay.get("incident_reproduced"):
        raise InvalidSessionStateError(
            "The historical recurrence must be reproduced before verification."
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
        "verified_at": _utc_now() if verified else None,
    }

    manifest["verification"] = verification

    if verified:
        manifest["status"] = "NON_RECURRENCE_VERIFIED"
        manifest["proof"] = {
            "status": "READY",
            "verified_at": verification["verified_at"],
        }
    else:
        manifest["status"] = "VERIFICATION_FAILED"
        manifest["proof"] = {
            "status": "FAILED",
            "verified_at": None,
        }

    _save_manifest(session_id, manifest)
    return verification


def generate_proof_of_non_recurrence(
    session_id: str,
) -> dict[str, Any]:
    """Generate the final evidence artifact for the known historical pattern."""
    manifest = load_session_manifest(session_id)
    _require_incident(manifest)
    _require_incident_memory(manifest)
    recurrence = _require_recurrence(manifest)

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
    memory_envelope = load_incident_memory(session_id)
    memory = (
        memory_envelope.get("memory", {})
        if memory_envelope
        else manifest.get("incident_memory", {}).get("memory", {})
    )

    proof = {
        "proof_type": "NoRepeat Proof of Non-Recurrence",
        "schema_version": 2,
        "session_id": session_id,
        "generated_at": _utc_now(),
        "repository": {
            "source": repository.get("source"),
            "source_type": repository.get("source_type"),
            "requested_revision": repository.get("requested_revision"),
            "resolved_revision": repository.get("resolved_revision"),
            "candidate_commit_sha": repository.get("commit_sha"),
        },
        "historical_incident": {
            "filename": incident.get("filename"),
            "sha256": incident.get("sha256"),
            "source": incident.get("source"),
        },
        "incident_memory": {
            "incident_id": memory.get("incident_id"),
            "root_cause": memory.get("root_cause"),
            "security_property": memory.get("security_property"),
            "historical_pattern": memory.get("historical_pattern"),
        },
        "recurrence_analysis": {
            "detected": recurrence.get("detected"),
            "summary": recurrence.get("summary"),
            "evidence": recurrence.get("evidence"),
        },
        "original_replay": {
            "incident_reproduced": replay.get("incident_reproduced"),
            "test_path": replay.get("test_path"),
        },
        "verification": {
            "incident_test_passed": verification["incident_test"]["success"],
            "full_test_suite_passed": verification["full_test_suite"]["success"],
        },
        "non_recurrence_verified": verification["verified"],
        "scope": (
            "This proof verifies non-recurrence only for the historical "
            "incident pattern represented by the persisted incident memory "
            "and the generated regression test. It is not a guarantee that "
            "the application contains no other vulnerabilities."
        ),
    }

    workspace = get_session_workspace(session_id)
    proof_path = workspace / "proof_of_non_recurrence.json"
    proof_path.write_text(
        json.dumps(proof, indent=2, ensure_ascii=False),
        encoding="utf-8",
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
    manifest["status"] = (
        "PROOF_VERIFIED"
        if proof["non_recurrence_verified"]
        else "PROOF_FAILED"
    )
    _save_manifest(session_id, manifest)
    return proof


def get_session_status(
    session_id: str,
) -> dict[str, Any]:
    manifest = load_session_manifest(session_id)

    return {
        "schema_version": manifest.get("schema_version"),
        "session_id": session_id,
        "status": manifest.get("status"),
        "repository": manifest.get("repository"),
        "incident": manifest.get("incident"),
        "incident_memory": manifest.get("incident_memory"),
        "baseline": manifest.get("baseline"),
        "baseline_completed": manifest.get("baseline") is not None,
        "incident_memory_ready": manifest.get("incident_memory") is not None,
        "recurrence_analysis": manifest.get("recurrence_analysis"),
        "recurrence_analysis_completed": (
            manifest.get("recurrence_analysis") is not None
        ),
        "incident_replay_completed": manifest.get("replay") is not None,
        "replay": manifest.get("replay"),
        "verification_completed": manifest.get("verification") is not None,
        "verification": manifest.get("verification"),
        "proof": manifest.get("proof"),
    }


def delete_session(session_id: str) -> bool:
    return remove_session_workspace(session_id)
