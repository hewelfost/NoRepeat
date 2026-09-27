from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.cleanup_manager import remove_session_evidence
from core.bob_runner import get_bob_runner
from core.incident_manager import (
    get_session_workspace,
    import_incident_file,
    load_incident_memory,
    save_incident_memory,
    save_uploaded_incident,
)
from core.repository_manager import (
    PROJECT_ROOT,
    WORKSPACES_DIR,
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




def _project_relative(path: Path) -> str:
    """Return a stable forward-slash path relative to the NoRepeat project root."""
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(PROJECT_ROOT.resolve())
    except ValueError as exc:
        raise OrchestratorError(
            f"Path is outside the NoRepeat project root: {resolved}"
        ) from exc
    return relative.as_posix()


def _load_bob_json_artifact(path: Path, *, label: str) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        raise OrchestratorError(
            f"IBM Bob completed the task but did not create the expected {label}: {path}"
        )

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise OrchestratorError(
            f"IBM Bob created an invalid JSON {label}: {path}"
        ) from exc

    if not isinstance(payload, dict) or not payload:
        raise OrchestratorError(
            f"IBM Bob {label} must be a non-empty JSON object."
        )

    return payload


def _validate_learned_memory(memory: dict[str, Any]) -> None:
    required = {
        "incident_id",
        "summary",
        "root_cause",
        "violated_security_property",
        "historical_failure_pattern",
        "recurrence_indicators",
    }
    missing = sorted(key for key in required if not memory.get(key))
    if missing:
        raise OrchestratorError(
            "IBM Bob incident memory is missing required field(s): "
            + ", ".join(missing)
        )

    if not isinstance(memory.get("recurrence_indicators"), list):
        raise OrchestratorError(
            "IBM Bob incident memory field 'recurrence_indicators' must be a list."
        )


def _validate_bob_recurrence_analysis(analysis: dict[str, Any]) -> None:
    required = {
        "incident_id",
        "recurrence_detected",
        "confidence",
        "historical_root_cause",
        "violated_security_property",
        "candidate_evidence",
        "semantic_correlation",
        "affected_files",
        "affected_behavior",
        "existing_test_gap",
        "recommended_regression_target",
    }
    missing = sorted(key for key in required if key not in analysis)
    if missing:
        raise OrchestratorError(
            "IBM Bob recurrence analysis is missing required field(s): "
            + ", ".join(missing)
        )

    if not isinstance(analysis.get("recurrence_detected"), bool):
        raise OrchestratorError(
            "IBM Bob recurrence analysis field 'recurrence_detected' must be boolean."
        )


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
        "regression_guard": None,
        "replay": None,
        "remediation": None,
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
    manifest["regression_guard"] = None
    manifest["replay"] = None
    manifest["remediation"] = None
    manifest["verification"] = None
    manifest["proof"] = {"status": "PENDING"}


def _clear_candidate_workspace_artifacts(session_id: str) -> None:
    """Delete generated files tied to the previous candidate revision.

    Incident Memory is historical knowledge and is intentionally preserved so a
    user can audit another branch/commit of the same repository without making
    Bob relearn the postmortem. Candidate-specific analysis, proof and generated
    repository artifacts must not survive a revision switch.
    """
    workspace = get_session_workspace(session_id)

    analysis_dir = workspace / "analysis"
    if analysis_dir.exists():
        for child in list(analysis_dir.iterdir()):
            # This artifact is derived only from the postmortem, not the
            # candidate code, so it may be reused across revisions.
            if child.name == "bob_incident_memory.json":
                continue
            if child.is_dir():
                import shutil
                shutil.rmtree(child)
            elif child.is_file():
                child.unlink()

    proof_path = workspace / "proof_of_non_recurrence.json"
    proof_path.unlink(missing_ok=True)


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
    _clear_candidate_workspace_artifacts(session_id)
    remove_session_evidence(session_id)
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
        exclude_generated_tests=True,
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



def learn_incident_with_bob(
    session_id: str,
) -> dict[str, Any]:
    """Ask IBM Bob to learn only from the user-supplied historical postmortem."""
    manifest = load_session_manifest(session_id)
    _require_incident(manifest)

    baseline = manifest.get("baseline")
    if baseline is None:
        raise InvalidSessionStateError(
            "Run the candidate baseline before asking IBM Bob to learn the incident."
        )
    if not baseline.get("success"):
        raise InvalidSessionStateError(
            "The candidate baseline must pass before IBM Bob learns the incident."
        )

    incident = manifest["incident"]
    incident_path = Path(str(incident.get("incident_path", ""))).resolve()
    if not incident_path.exists():
        raise OrchestratorError(
            "The historical incident file referenced by the session no longer exists."
        )

    workspace = get_session_workspace(session_id)
    analysis_dir = workspace / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    output_path = analysis_dir / "bob_incident_memory.json"
    output_path.unlink(missing_ok=True)

    incident_ref = _project_relative(incident_path)
    output_ref = _project_relative(output_path)

    prompt = f"""
Perform only the Learn phase for NoRepeat session {session_id}.

Historical postmortem supplied by the user:
@{incident_ref}

Rules:
- Learn only from the historical postmortem.
- Do not inspect the candidate repository.
- Do not generate tests.
- Do not modify application code.
- Do not apply remediation.
- Do not invent facts that are not supported by the postmortem.

Create exactly one structured JSON object at:
{output_ref}

Required fields:
- incident_id
- summary
- root_cause
- violated_security_property
- historical_failure_pattern
- affected_behavior
- recurrence_indicators
- remediation_constraints

The recurrence_indicators field must be a JSON array.
Validate the JSON before finishing.
Do not wrap the file contents in Markdown fences.

At the end, report only that the memory artifact was created and validated.
""".strip()

    bob_result = get_bob_runner().run_norepeat(
        prompt,
        max_cost=0.40,
        max_turns=8,
        timeout_seconds=600,
        allow_subagents=False,
    )

    memory = _load_bob_json_artifact(
        output_path,
        label="incident memory artifact",
    )
    _validate_learned_memory(memory)

    updated_manifest = record_incident_memory(
        session_id=session_id,
        memory=memory,
    )
    updated_manifest["incident_memory"]["bob_execution"] = {
        "task_id": bob_result.task_id,
        "status": bob_result.status,
        "stats": bob_result.stats,
        "last_message": bob_result.last_message,
        "artifact_path": str(output_path.resolve()),
    }
    updated_manifest["status"] = "INCIDENT_MEMORY_READY"
    _save_manifest(session_id, updated_manifest)

    return {
        "incident_memory": updated_manifest["incident_memory"],
        "bob": bob_result.to_dict(),
    }


def analyze_recurrence_with_bob(
    session_id: str,
) -> dict[str, Any]:
    """Ask IBM Bob to compare the candidate revision with persisted incident memory."""
    manifest = load_session_manifest(session_id)
    _require_incident(manifest)
    _require_incident_memory(manifest)

    baseline = manifest.get("baseline")
    if baseline is None or not baseline.get("success"):
        raise InvalidSessionStateError(
            "A passing candidate baseline is required before recurrence analysis."
        )

    workspace = get_session_workspace(session_id)
    repository_path = Path(
        str((manifest.get("repository") or {}).get("repository_path", ""))
    ).resolve()
    if not repository_path.exists() or not repository_path.is_dir():
        raise OrchestratorError(
            "The candidate repository referenced by this session no longer exists."
        )

    memory_path_raw = (manifest.get("incident_memory") or {}).get("memory_path")
    if not memory_path_raw:
        raise OrchestratorError("Persisted incident memory path is missing.")
    memory_path = Path(str(memory_path_raw)).resolve()
    if not memory_path.exists():
        raise OrchestratorError("Persisted incident memory file no longer exists.")

    analysis_dir = workspace / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    output_path = analysis_dir / "recurrence.json"
    output_path.unlink(missing_ok=True)

    memory_ref = _project_relative(memory_path)
    repository_ref = _project_relative(repository_path)
    output_ref = _project_relative(output_path)

    prompt = f"""
Perform only the Analyze phase for NoRepeat session {session_id}.

Historical Incident Memory:
@{memory_ref}

Candidate repository:
@{repository_ref}

Goal:
Determine whether the current candidate revision semantically repeats the historical root cause described in Incident Memory.

Use up to 3 read-only parallel subagents when useful:
1. Historical Pattern Analyst — identify the root cause, security property, and recurrence indicators.
2. Candidate Code Analyst — inspect relevant behavior and controls in the candidate repository.
3. Existing Tests Analyst — determine whether existing tests enforce the historical security property.

Rules:
- Do not assume recurrence exists.
- Do not classify recurrence from keyword similarity alone.
- Require concrete behavioral evidence.
- Do not modify application code.
- Do not generate regression tests.
- Do not apply remediation.

Persist the result as valid JSON at:
{output_ref}

Required fields:
- incident_id
- recurrence_detected
- confidence
- historical_root_cause
- violated_security_property
- candidate_evidence
- semantic_correlation
- affected_files
- affected_behavior
- existing_test_gap
- recommended_regression_target

recurrence_detected must be a JSON boolean.
Validate the JSON before finishing.
Do not wrap the file contents in Markdown fences.

At the end report only:
- recurrence detected: yes/no
- affected component(s)
- semantic reason
- existing test gap
- generated analysis file
- validation result
""".strip()

    bob_result = get_bob_runner().run_norepeat(
        prompt,
        max_cost=0.80,
        max_turns=12,
        timeout_seconds=900,
        allow_subagents=True,
    )

    analysis = _load_bob_json_artifact(
        output_path,
        label="recurrence analysis artifact",
    )
    _validate_bob_recurrence_analysis(analysis)

    recorded = record_recurrence_analysis(
        session_id=session_id,
        analysis=analysis,
    )

    refreshed = load_session_manifest(session_id)
    refreshed["recurrence_analysis"]["bob_execution"] = {
        "task_id": bob_result.task_id,
        "status": bob_result.status,
        "stats": bob_result.stats,
        "last_message": bob_result.last_message,
        "artifact_path": str(output_path.resolve()),
    }
    _save_manifest(session_id, refreshed)

    return {
        "analysis": refreshed["recurrence_analysis"],
        "bob": bob_result.to_dict(),
    }


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

    baseline = manifest.get("baseline")
    if baseline is None:
        raise InvalidSessionStateError(
            "Run the project baseline before recording recurrence analysis."
        )
    if not baseline.get("success"):
        raise InvalidSessionStateError(
            "The candidate baseline must pass before recurrence analysis can be recorded."
        )

    if not isinstance(analysis, dict) or not analysis:
        raise OrchestratorError(
            "Recurrence analysis must be a non-empty JSON object."
        )

    # Bob's analysis schema uses recurrence_detected. Older/manual integration
    # used detected. Accept both, reject conflicts, and normalize to detected so
    # the rest of NoRepeat has one canonical field.
    detected = analysis.get("detected")
    bob_detected = analysis.get("recurrence_detected")

    if detected is None:
        detected = bob_detected
    elif isinstance(bob_detected, bool) and bob_detected != detected:
        raise OrchestratorError(
            "Recurrence analysis contains conflicting detection fields."
        )

    if not isinstance(detected, bool):
        raise OrchestratorError(
            "Recurrence analysis must include boolean 'detected' or "
            "'recurrence_detected'."
        )

    repository = manifest.get("repository") or {}
    enriched = dict(analysis)
    enriched["detected"] = detected
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
    manifest["regression_guard"] = None
    manifest["replay"] = None
    manifest["remediation"] = None
    manifest["verification"] = None
    manifest["proof"] = {"status": "PENDING"}
    manifest["status"] = (
        "RECURRENCE_DETECTED"
        if detected
        else "NO_KNOWN_RECURRENCE"
    )
    _save_manifest(session_id, manifest)
    return enriched


def _guard_filename(incident_id: str) -> str:
    """Return a stable pytest filename for one historical incident id."""
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", str(incident_id)).strip("_")
    if not cleaned:
        cleaned = "incident"
    return f"test_{cleaned}.py"


def _require_regression_guard(manifest: dict[str, Any]) -> dict[str, Any]:
    guard = manifest.get("regression_guard")
    if not guard:
        raise InvalidSessionStateError(
            "Generate the IBM Bob regression guard before replaying the incident."
        )
    return guard


def generate_regression_guard_with_bob(
    session_id: str,
) -> dict[str, Any]:
    """Ask IBM Bob to generate only the regression test for a detected recurrence."""
    manifest = load_session_manifest(session_id)
    _require_incident(manifest)
    _require_incident_memory(manifest)
    analysis = _require_recurrence(manifest)

    baseline = manifest.get("baseline") or {}
    if not baseline.get("success"):
        raise InvalidSessionStateError(
            "A passing candidate baseline is required before guard generation."
        )

    repository_path = Path(
        str((manifest.get("repository") or {}).get("repository_path", ""))
    ).resolve()
    if not repository_path.exists() or not repository_path.is_dir():
        raise OrchestratorError(
            "The candidate repository referenced by this session no longer exists."
        )

    memory_path_raw = (manifest.get("incident_memory") or {}).get("memory_path")
    if not memory_path_raw:
        raise OrchestratorError("Persisted incident memory path is missing.")
    memory_path = Path(str(memory_path_raw)).resolve()
    if not memory_path.exists():
        raise OrchestratorError("Persisted incident memory file no longer exists.")

    workspace = get_session_workspace(session_id)
    analysis_dir = workspace / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    recurrence_path = analysis_dir / "recurrence.json"

    # Keep a canonical analysis artifact available even if the original Bob-created
    # file was removed after the analysis had already been persisted in the manifest.
    if not recurrence_path.exists():
        recurrence_payload = {
            key: value
            for key, value in analysis.items()
            if key not in {"bob_execution", "evidence_path", "recorded_at"}
        }
        recurrence_path.write_text(
            json.dumps(recurrence_payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    memory = (manifest.get("incident_memory") or {}).get("memory") or {}
    incident_id = str(memory.get("incident_id") or analysis.get("incident_id") or "INCIDENT")

    generated_dir = repository_path / "tests" / "generated"
    generated_dir.mkdir(parents=True, exist_ok=True)
    output_path = generated_dir / _guard_filename(incident_id)
    output_path.unlink(missing_ok=True)

    memory_ref = _project_relative(memory_path)
    recurrence_ref = _project_relative(recurrence_path)
    repository_ref = _project_relative(repository_path)
    output_ref = _project_relative(output_path)

    prompt = f"""
Perform only the Test phase for NoRepeat session {session_id}.

Historical Incident Memory:
@{memory_ref}

Persisted recurrence analysis:
@{recurrence_ref}

Candidate repository:
@{repository_ref}

Goal:
Create one deterministic pytest regression test that proves the concrete detected
recurrence and permanently encodes the historical security property.

Write exactly one test file at:
{output_ref}

Rules:
- Use the candidate repository's existing pytest conventions and fixtures.
- Target the concrete behavior identified by recurrence.json.
- The test must encode the historical security property, not merely check keywords.
- The test should FAIL on the current recurring revision for the expected security reason.
- The test should PASS after a correct minimal remediation.
- Do not modify production/application code.
- Do not modify existing baseline tests.
- Do not delete, skip, xfail, weaken, or bypass the generated regression test.
- Do not apply remediation in this phase.
- Do not create additional files outside the requested regression test.
- Do not perform network calls from the test.
- Do not execute pytest yet; NoRepeat will perform replay independently.
- You may validate Python syntax only.

At the end report only:
- generated test path
- behavior guarded
- why the current candidate should fail it
- syntax validation result
""".strip()

    bob_result = get_bob_runner().run_norepeat(
        prompt,
        max_cost=0.55,
        max_turns=8,
        timeout_seconds=600,
        allow_subagents=False,
    )

    if not output_path.exists() or not output_path.is_file():
        raise OrchestratorError(
            "IBM Bob completed guard generation but did not create the expected "
            f"regression test: {output_path}"
        )

    source = output_path.read_text(encoding="utf-8")
    if not source.strip():
        raise OrchestratorError("IBM Bob generated an empty regression test file.")

    try:
        compile(source, str(output_path), "exec")
    except SyntaxError as exc:
        raise OrchestratorError(
            f"IBM Bob generated a regression test with invalid Python syntax: {exc}"
        ) from exc

    test_path = output_path.relative_to(repository_path).as_posix()
    guard = {
        "incident_id": incident_id,
        "test_path": test_path,
        "absolute_path": str(output_path.resolve()),
        "created_at": _utc_now(),
        "behavior_guarded": analysis.get("affected_behavior"),
        "security_property": analysis.get("violated_security_property"),
        "bob_execution": {
            "task_id": bob_result.task_id,
            "status": bob_result.status,
            "stats": bob_result.stats,
            "last_message": bob_result.last_message,
        },
    }

    manifest["regression_guard"] = guard
    manifest["replay"] = None
    manifest["remediation"] = None
    manifest["verification"] = None
    manifest["proof"] = {"status": "PENDING"}
    manifest["status"] = "REGRESSION_GUARD_READY"
    _save_manifest(session_id, manifest)

    return {
        "guard": guard,
        "bob": bob_result.to_dict(),
    }


def replay_incident(
    session_id: str,
    incident_test_path: str,
) -> dict[str, Any]:
    """Execute Bob's regression test after recurrence has been detected."""
    manifest = load_session_manifest(session_id)
    _require_incident(manifest)
    _require_incident_memory(manifest)
    _require_recurrence(manifest)
    guard = _require_regression_guard(manifest)

    if manifest.get("remediation"):
        raise InvalidSessionStateError(
            "The candidate has already been remediated. Preserve the original "
            "pre-remediation replay evidence and continue with verification."
        )

    expected_test_path = str(guard.get("test_path") or "").strip()
    if not expected_test_path:
        raise OrchestratorError("Generated regression guard test path is missing.")
    if incident_test_path.strip().replace("\\", "/") != expected_test_path:
        raise InvalidSessionStateError(
            "Replay must use the regression test generated by IBM Bob: "
            + expected_test_path
        )

    result = run_incident_replay(
        session_id=session_id,
        incident_test_path=incident_test_path,
        evidence_label="before-fix",
    )

    counters = result.get("results") or {}
    incident_reproduced = (
        result.get("status") == "FAIL"
        and result.get("return_code") == 1
        and int(counters.get("failed", 0)) > 0
        and int(counters.get("errors", 0)) == 0
    )
    replay_valid = result.get("status") in {"PASS", "FAIL"}

    replay_data = {
        "test_path": incident_test_path,
        "pytest": result,
        "incident_reproduced": incident_reproduced,
        "replay_valid": replay_valid,
        "candidate_commit_sha": (
            manifest.get("repository", {}).get("commit_sha")
        ),
    }

    manifest["replay"] = replay_data
    manifest["remediation"] = None
    manifest["verification"] = None
    manifest["proof"] = {"status": "PENDING"}
    if incident_reproduced:
        manifest["status"] = "INCIDENT_REPRODUCED"
    elif replay_valid:
        manifest["status"] = "INCIDENT_NOT_REPRODUCED"
    else:
        manifest["status"] = "REPLAY_ERROR"
    _save_manifest(session_id, manifest)
    return replay_data



def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _repository_file_hashes(repository_path: Path) -> dict[str, str]:
    """Hash relevant repository files so Bob's remediation can be audited."""
    hashes: dict[str, str] = {}
    ignored_parts = {
        ".git",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
    }
    ignored_names = {".coverage", "coverage.xml"}

    for path in repository_path.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(repository_path)
        if any(part in ignored_parts for part in relative.parts):
            continue
        if path.name in ignored_names or path.suffix in {".pyc", ".pyo"}:
            continue
        try:
            hashes[relative.as_posix()] = _sha256_file(path)
        except OSError as exc:
            raise OrchestratorError(
                f"Unable to fingerprint candidate file during remediation: {path}"
            ) from exc
    return hashes


def _changed_paths(before: dict[str, str], after: dict[str, str]) -> list[str]:
    keys = set(before) | set(after)
    return sorted(key for key in keys if before.get(key) != after.get(key))


def remediate_with_bob(
    session_id: str,
) -> dict[str, Any]:
    """Ask IBM Bob to apply only the smallest justified production-code fix."""
    manifest = load_session_manifest(session_id)
    _require_incident(manifest)
    _require_incident_memory(manifest)
    analysis = _require_recurrence(manifest)
    guard = _require_regression_guard(manifest)

    replay = manifest.get("replay") or {}
    if not replay.get("incident_reproduced"):
        raise InvalidSessionStateError(
            "The historical recurrence must be reproduced by the generated guard "
            "before IBM Bob is allowed to remediate it."
        )

    existing_remediation = manifest.get("remediation")
    existing_verification = manifest.get("verification") or {}
    if existing_remediation and not (
        existing_verification and not existing_verification.get("verified")
    ):
        raise InvalidSessionStateError(
            "IBM Bob remediation has already been applied. Run independent "
            "verification before requesting another remediation attempt."
        )

    repository_path = Path(
        str((manifest.get("repository") or {}).get("repository_path", ""))
    ).resolve()
    if not repository_path.exists() or not repository_path.is_dir():
        raise OrchestratorError(
            "The candidate repository referenced by this session no longer exists."
        )

    memory_path_raw = (manifest.get("incident_memory") or {}).get("memory_path")
    if not memory_path_raw:
        raise OrchestratorError("Persisted incident memory path is missing.")
    memory_path = Path(str(memory_path_raw)).resolve()
    if not memory_path.exists():
        raise OrchestratorError("Persisted incident memory file no longer exists.")

    workspace = get_session_workspace(session_id)
    recurrence_path = workspace / "analysis" / "recurrence.json"
    if not recurrence_path.exists():
        recurrence_payload = {
            key: value
            for key, value in analysis.items()
            if key not in {"bob_execution", "evidence_path", "recorded_at"}
        }
        recurrence_path.parent.mkdir(parents=True, exist_ok=True)
        recurrence_path.write_text(
            json.dumps(recurrence_payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    guard_test_path = str(guard.get("test_path") or "").strip()
    if not guard_test_path:
        raise OrchestratorError("Generated regression guard path is missing.")
    guard_path = (repository_path / guard_test_path).resolve()
    try:
        guard_path.relative_to(repository_path)
    except ValueError as exc:
        raise OrchestratorError(
            "Generated regression guard resolves outside the candidate repository."
        ) from exc
    if not guard_path.exists() or not guard_path.is_file():
        raise OrchestratorError(
            f"Generated regression guard no longer exists: {guard_test_path}"
        )

    before_repo = _repository_file_hashes(repository_path)
    before_tests = {
        path: digest
        for path, digest in before_repo.items()
        if path == "tests" or path.startswith("tests/")
    }
    guard_sha_before = _sha256_file(guard_path)
    memory_sha_before = _sha256_file(memory_path)
    recurrence_sha_before = _sha256_file(recurrence_path)

    memory_ref = _project_relative(memory_path)
    recurrence_ref = _project_relative(recurrence_path)
    repository_ref = _project_relative(repository_path)
    guard_ref = _project_relative(guard_path)

    prompt = f"""
Perform only the Remediate phase for NoRepeat session {session_id}.

Historical Incident Memory:
@{memory_ref}

Persisted recurrence analysis:
@{recurrence_ref}

Candidate repository:
@{repository_ref}

Failing regression guard that independently reproduced the historical recurrence:
@{guard_ref}

Goal:
Apply the smallest justified production-code remediation that restores the historical
security property while preserving the regression evidence and unrelated behavior.

Rules:
- Modify only candidate production/application code required for the fix.
- Do not modify, delete, rename, skip, xfail, weaken, or replace any test file.
- The generated regression guard is immutable evidence.
- Do not modify Incident Memory, recurrence.json, NoRepeat manifests, or evidence files.
- Do not add a second workaround test or bypass the failing assertion.
- Do not perform unrelated refactors or formatting sweeps.
- Do not commit, push, or change Git branches.
- Preserve existing public behavior except where the historical security property
  requires the minimal change.
- You may inspect existing code and test conventions.
- You may run the generated regression test for feedback, but NoRepeat will perform
  the independent final verification and full-suite run after you finish.

At the end report only:
- files changed
- minimal remediation applied
- historical security property restored
- regression test preserved: yes/no
""".strip()

    bob_result = get_bob_runner().run_norepeat(
        prompt,
        max_cost=0.70,
        max_turns=10,
        timeout_seconds=900,
        allow_subagents=False,
    )

    after_repo = _repository_file_hashes(repository_path)
    after_tests = {
        path: digest
        for path, digest in after_repo.items()
        if path == "tests" or path.startswith("tests/")
    }

    if before_tests != after_tests:
        changed_tests = _changed_paths(before_tests, after_tests)
        raise OrchestratorError(
            "IBM Bob modified protected test evidence during remediation. "
            "NoRepeat rejected the remediation. Changed test path(s): "
            + ", ".join(changed_tests)
        )

    if _sha256_file(guard_path) != guard_sha_before:
        raise OrchestratorError(
            "IBM Bob changed the generated regression guard during remediation. "
            "NoRepeat rejected the remediation."
        )

    if _sha256_file(memory_path) != memory_sha_before:
        raise OrchestratorError(
            "IBM Bob changed persisted Incident Memory during remediation. "
            "NoRepeat rejected the remediation."
        )

    if _sha256_file(recurrence_path) != recurrence_sha_before:
        raise OrchestratorError(
            "IBM Bob changed recurrence evidence during remediation. "
            "NoRepeat rejected the remediation."
        )

    changed_files = _changed_paths(before_repo, after_repo)
    production_changes = [
        path for path in changed_files if not path.startswith("tests/")
    ]
    if not production_changes:
        raise OrchestratorError(
            "IBM Bob completed remediation without changing candidate production code."
        )

    attempt = 1
    if isinstance(existing_remediation, dict):
        attempt = int(existing_remediation.get("attempt", 0) or 0) + 1

    remediation = {
        "status": "APPLIED",
        "attempt": attempt,
        "applied_at": _utc_now(),
        "changed_files": production_changes,
        "all_repository_changes": changed_files,
        "regression_guard_path": guard_test_path,
        "regression_guard_sha256": guard_sha_before,
        "protected_tests_preserved": True,
        "incident_memory_preserved": True,
        "recurrence_evidence_preserved": True,
        "candidate_commit_sha": (
            manifest.get("repository", {}).get("commit_sha")
        ),
        "bob_execution": {
            "task_id": bob_result.task_id,
            "status": bob_result.status,
            "stats": bob_result.stats,
            "last_message": bob_result.last_message,
        },
    }

    manifest["remediation"] = remediation
    manifest["verification"] = None
    manifest["proof"] = {"status": "PENDING"}
    manifest["status"] = "BOB_REMEDIATION_APPLIED"
    _save_manifest(session_id, manifest)

    return {
        "remediation": remediation,
        "bob": bob_result.to_dict(),
    }

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

    remediation = manifest.get("remediation") or {}
    if remediation.get("status") != "APPLIED":
        raise InvalidSessionStateError(
            "IBM Bob must apply remediation before independent verification."
        )

    replay_test = Path(str(replay.get("test_path", ""))).as_posix().strip()
    requested_test = Path(incident_test_path).as_posix().strip()
    if not replay_test or replay_test != requested_test:
        raise InvalidSessionStateError(
            "Verification must use the same regression test that reproduced the incident."
        )

    repository_path = Path(
        str((manifest.get("repository") or {}).get("repository_path", ""))
    ).resolve()
    guard_path = (repository_path / requested_test).resolve()
    expected_guard_sha = str(remediation.get("regression_guard_sha256") or "")
    if not guard_path.exists() or not guard_path.is_file():
        raise OrchestratorError(
            "The immutable regression guard is missing before verification."
        )
    if expected_guard_sha and _sha256_file(guard_path) != expected_guard_sha:
        raise InvalidSessionStateError(
            "The regression guard changed after remediation. Verification was blocked "
            "to preserve evidence integrity."
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
        "remediation_attempt": remediation.get("attempt"),
        "regression_guard_sha256": expected_guard_sha,
    }

    manifest["verification"] = verification
    manifest["remediation"]["verification_status"] = (
        "VERIFIED" if verified else "FAILED"
    )
    manifest["remediation"]["verified_at"] = verification["verified_at"]

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
    if not verification.get("verified"):
        raise InvalidSessionStateError(
            "Proof of Non-Recurrence requires a passing independent verification."
        )

    remediation = manifest.get("remediation") or {}
    if remediation.get("status") != "APPLIED":
        raise InvalidSessionStateError(
            "Proof of Non-Recurrence requires recorded IBM Bob remediation evidence."
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
            "security_property": (
                memory.get("security_property")
                or memory.get("violated_security_property")
            ),
            "historical_pattern": (
                memory.get("historical_pattern")
                or memory.get("historical_failure_pattern")
            ),
        },
        "recurrence_analysis": {
            "detected": recurrence.get("detected"),
            "summary": (
                recurrence.get("summary")
                or recurrence.get("semantic_correlation")
            ),
            "evidence": (
                recurrence.get("evidence")
                or recurrence.get("candidate_evidence")
            ),
        },
        "original_replay": {
            "incident_reproduced": replay.get("incident_reproduced"),
            "test_path": replay.get("test_path"),
        },
        "remediation": {
            "status": remediation.get("status"),
            "attempt": remediation.get("attempt"),
            "applied_at": remediation.get("applied_at"),
            "changed_files": remediation.get("changed_files"),
            "protected_tests_preserved": remediation.get(
                "protected_tests_preserved"
            ),
            "incident_memory_preserved": remediation.get(
                "incident_memory_preserved"
            ),
            "recurrence_evidence_preserved": remediation.get(
                "recurrence_evidence_preserved"
            ),
            "bob_task_id": (remediation.get("bob_execution") or {}).get(
                "task_id"
            ),
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
        "regression_guard": manifest.get("regression_guard"),
        "regression_guard_ready": manifest.get("regression_guard") is not None,
        "incident_replay_completed": manifest.get("replay") is not None,
        "replay": manifest.get("replay"),
        "remediation_completed": manifest.get("remediation") is not None,
        "remediation": manifest.get("remediation"),
        "verification_completed": manifest.get("verification") is not None,
        "verification": manifest.get("verification"),
        "proof": manifest.get("proof"),
    }


def list_sessions() -> list[dict[str, Any]]:
    """Return resumable NoRepeat sessions, newest first.

    Invalid/incomplete workspace folders are skipped instead of breaking the UI.
    """
    sessions: list[dict[str, Any]] = []

    if not WORKSPACES_DIR.exists():
        return sessions

    for workspace in WORKSPACES_DIR.iterdir():
        if not workspace.is_dir():
            continue

        manifest_path = workspace / SESSION_MANIFEST_NAME
        if not manifest_path.exists() or not manifest_path.is_file():
            continue

        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue

        if not isinstance(manifest, dict):
            continue

        repository = manifest.get("repository") or {}
        incident = manifest.get("incident") or {}
        sessions.append(
            {
                "session_id": manifest.get("session_id") or workspace.name,
                "status": manifest.get("status"),
                "created_at": manifest.get("created_at"),
                "updated_at": manifest.get("updated_at"),
                "repository": {
                    "source_type": repository.get("source_type"),
                    "source": repository.get("source"),
                    "requested_revision": repository.get("requested_revision"),
                    "resolved_revision": repository.get("resolved_revision"),
                    "commit_sha": repository.get("commit_sha"),
                },
                "incident": {
                    "filename": incident.get("filename"),
                } if incident else None,
                "baseline_passed": bool((manifest.get("baseline") or {}).get("success")),
                "recurrence_detected": bool((manifest.get("recurrence_analysis") or {}).get("detected")),
                "proof_status": (manifest.get("proof") or {}).get("status"),
            }
        )

    sessions.sort(
        key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""),
        reverse=True,
    )
    return sessions


def delete_session(session_id: str) -> bool:
    removed = remove_session_workspace(session_id)
    if removed:
        remove_session_evidence(session_id)
    return removed
