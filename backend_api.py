from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge

from core.cleanup_manager import cleanup_generated_runtime_data
from core.bob_runner import (
    BobExecutionError,
    BobOutputError,
    BobRunnerError,
    BobShellNotFoundError,
    BobTimeoutError,
)
from core.incident_manager import (
    IncidentManagerError,
    InvalidIncidentFileError,
    InvalidIncidentMemoryError,
    SessionNotFoundError,
)
from core.orchestrator import (
    InvalidSessionStateError,
    OrchestratorError,
    analyze_recurrence_with_bob,
    attach_uploaded_incident,
    create_session_from_github,
    create_session_from_zip,
    delete_session,
    generate_proof_of_non_recurrence,
    generate_regression_guard_with_bob,
    get_session_status,
    learn_incident_with_bob,
    list_sessions,
    record_incident_memory,
    record_recurrence_analysis,
    remediate_with_bob,
    replay_incident,
    run_baseline,
    set_candidate_revision,
    verify_after_fix,
)
from core.repository_manager import (
    InvalidRepositoryURLError,
    InvalidRevisionError,
    RepositoryCloneError,
    RepositoryManagerError,
    ZipExtractionError,
)
from core.replay_engine import (
    InvalidTestTargetError,
    ReplayEngineError,
    ReplayTimeoutError,
    RepositoryNotFoundError,
)


app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024  # 25 MB


def api_response(
    data: Any = None,
    message: str | None = None,
    status_code: int = 200,
):
    payload = {
        "success": status_code < 400,
        "message": message,
        "data": data,
    }
    return jsonify(payload), status_code


def get_json_body() -> dict:
    if not request.is_json:
        raise ValueError(
            "Request body must use application/json."
        )

    body = request.get_json(silent=True)

    if not isinstance(body, dict):
        raise ValueError(
            "Request body must contain a valid JSON object."
        )

    return body


def require_cleanup_authorization() -> None:
    """Protect destructive runtime cleanup when a token is configured."""
    expected_token = os.getenv("NOREPEAT_CLEANUP_TOKEN", "").strip()
    if not expected_token:
        return

    supplied_token = request.headers.get("X-NoRepeat-Cleanup-Token", "")
    if supplied_token != expected_token:
        raise PermissionError("Invalid cleanup authorization token.")


@app.get("/")
def root():
    return api_response(
        data={
            "service": "NoRepeat API",
            "version": 2,
        },
        message="NoRepeat API is online.",
    )


@app.get("/api/health")
def health():
    return api_response(
        data={
            "service": "NoRepeat API",
            "status": "healthy",
            "workflow": "historical-recurrence",
        },
        message="NoRepeat backend is running.",
    )


@app.post("/api/runtime/cleanup")
def cleanup_runtime():
    """Hard-reset generated runtime artifacts while preserving project defaults."""
    require_cleanup_authorization()
    report = cleanup_generated_runtime_data()
    return api_response(
        data=report,
        message=(
            "Generated runtime data cleaned successfully. "
            "Bob project configuration and predefined source assets were preserved."
        ),
    )


@app.get("/api/sessions")
def sessions_index():
    """List resumable NoRepeat sessions, newest first."""
    return api_response(
        data=list_sessions(),
        message="Resumable sessions retrieved.",
    )


@app.post("/api/sessions/github")
def create_github_session():
    """
    Create a session for a GitHub repository and optional revision.

    JSON:
        {
            "repository_url": "https://github.com/owner/repository",
            "revision": "feature/branch-or-commit"  // optional
        }
    """
    body = get_json_body()
    repository_url = body.get("repository_url")
    revision = body.get("revision")

    if not isinstance(repository_url, str) or not repository_url.strip():
        return api_response(
            message="repository_url is required.",
            status_code=400,
        )

    if revision is not None and not isinstance(revision, str):
        return api_response(
            message="revision must be a string when provided.",
            status_code=400,
        )

    manifest = create_session_from_github(
        repository_url=repository_url,
        revision=revision,
    )

    return api_response(
        data=manifest,
        message="GitHub candidate revision loaded successfully.",
        status_code=201,
    )


@app.post("/api/sessions/zip")
def create_zip_session():
    """Create a NoRepeat session from an uploaded ZIP snapshot."""
    uploaded_file = request.files.get("project")

    if uploaded_file is None:
        return api_response(
            message="ZIP project upload is required.",
            status_code=400,
        )

    filename = uploaded_file.filename or ""

    if not filename.lower().endswith(".zip"):
        return api_response(
            message="Only .zip project uploads are supported.",
            status_code=400,
        )

    temp_path: Path | None = None

    try:
        with tempfile.NamedTemporaryFile(
            prefix="norepeat-upload-",
            suffix=".zip",
            delete=False,
        ) as temporary_file:
            uploaded_file.save(temporary_file)
            temp_path = Path(temporary_file.name)

        manifest = create_session_from_zip(
            zip_path=temp_path,
        )

        return api_response(
            data=manifest,
            message="ZIP candidate snapshot loaded successfully.",
            status_code=201,
        )
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink(missing_ok=True)


@app.patch("/api/sessions/<session_id>/revision")
def change_revision(session_id: str):
    """Switch a GitHub session to another branch, tag, or commit."""
    body = get_json_body()
    revision = body.get("revision")

    if not isinstance(revision, str) or not revision.strip():
        return api_response(
            message="revision is required.",
            status_code=400,
        )

    manifest = set_candidate_revision(
        session_id=session_id,
        revision=revision,
    )

    return api_response(
        data=manifest,
        message=(
            "Candidate revision changed. Historical incident memory was "
            "preserved and candidate-specific evidence was reset."
        ),
    )


@app.post("/api/sessions/<session_id>/incident")
def upload_incident(session_id: str):
    """Attach the historical postmortem supplied by the user."""
    uploaded_file = request.files.get("incident")

    if uploaded_file is None:
        return api_response(
            message="Historical postmortem upload is required.",
            status_code=400,
        )

    filename = uploaded_file.filename or ""

    if not filename:
        return api_response(
            message="Incident filename is required.",
            status_code=400,
        )

    manifest = attach_uploaded_incident(
        session_id=session_id,
        filename=filename,
        content=uploaded_file.read(),
    )

    return api_response(
        data=manifest,
        message="Historical postmortem attached successfully.",
    )


@app.post("/api/sessions/<session_id>/baseline")
def baseline(session_id: str):
    result = run_baseline(session_id=session_id)
    return api_response(
        data=result,
        message="Candidate baseline test suite completed.",
    )


@app.post("/api/sessions/<session_id>/bob/learn")
def bob_learn_incident(session_id: str):
    result = learn_incident_with_bob(session_id=session_id)
    return api_response(
        data=result,
        message="IBM Bob learned and persisted the historical incident memory.",
    )


@app.post("/api/sessions/<session_id>/bob/analyze")
def bob_analyze_recurrence(session_id: str):
    result = analyze_recurrence_with_bob(session_id=session_id)
    return api_response(
        data=result,
        message="IBM Bob completed and persisted the recurrence analysis.",
    )


@app.post("/api/sessions/<session_id>/bob/generate-guard")
def bob_generate_regression_guard(session_id: str):
    result = generate_regression_guard_with_bob(session_id=session_id)
    return api_response(
        data=result,
        message="IBM Bob generated and registered the historical regression guard.",
    )


@app.post("/api/sessions/<session_id>/bob/remediate")
def bob_remediate(session_id: str):
    result = remediate_with_bob(session_id=session_id)
    return api_response(
        data=result,
        message=(
            "IBM Bob applied the minimal remediation while preserving "
            "the regression evidence."
        ),
    )


@app.post("/api/sessions/<session_id>/incident-memory")
def incident_memory(session_id: str):
    """
    Future Bob integration endpoint.

    Bob will send its structured understanding of the user postmortem here.
    """
    body = get_json_body()
    memory = body.get("memory")

    if not isinstance(memory, dict) or not memory:
        return api_response(
            message="memory must be a non-empty JSON object.",
            status_code=400,
        )

    manifest = record_incident_memory(
        session_id=session_id,
        memory=memory,
    )

    return api_response(
        data=manifest,
        message="Historical incident memory stored successfully.",
    )


@app.post("/api/sessions/<session_id>/recurrence-analysis")
def recurrence_analysis(session_id: str):
    """
    Future Bob integration endpoint.

    Bob will send the semantic comparison between incident memory and the
    selected candidate revision here.
    """
    body = get_json_body()
    analysis = body.get("analysis")

    if not isinstance(analysis, dict) or not analysis:
        return api_response(
            message="analysis must be a non-empty JSON object.",
            status_code=400,
        )

    result = record_recurrence_analysis(
        session_id=session_id,
        analysis=analysis,
    )

    return api_response(
        data=result,
        message="Historical recurrence analysis stored successfully.",
    )


@app.post("/api/sessions/<session_id>/replay")
def incident_replay(session_id: str):
    body = get_json_body()
    incident_test_path = body.get("incident_test_path")

    if not isinstance(incident_test_path, str) or not incident_test_path.strip():
        return api_response(
            message="incident_test_path is required.",
            status_code=400,
        )

    result = replay_incident(
        session_id=session_id,
        incident_test_path=incident_test_path.strip(),
    )

    return api_response(
        data=result,
        message=(
            "Historical recurrence replay completed. "
            "Review incident_reproduced for the result."
        ),
    )


@app.post("/api/sessions/<session_id>/verify")
def verify(session_id: str):
    body = get_json_body()
    incident_test_path = body.get("incident_test_path")

    if not isinstance(incident_test_path, str) or not incident_test_path.strip():
        return api_response(
            message="incident_test_path is required.",
            status_code=400,
        )

    result = verify_after_fix(
        session_id=session_id,
        incident_test_path=incident_test_path.strip(),
    )

    return api_response(
        data=result,
        message="Post-remediation verification completed.",
    )


@app.post("/api/sessions/<session_id>/proof")
def generate_proof(session_id: str):
    proof = generate_proof_of_non_recurrence(
        session_id=session_id,
    )
    return api_response(
        data=proof,
        message="Proof of Non-Recurrence generated.",
    )


@app.get("/api/sessions/<session_id>")
def session_status(session_id: str):
    status = get_session_status(session_id=session_id)
    return api_response(
        data=status,
        message="Session status retrieved.",
    )


@app.delete("/api/sessions/<session_id>")
def remove_session(session_id: str):
    removed = delete_session(session_id=session_id)

    if not removed:
        return api_response(
            message="Session was not found.",
            status_code=404,
        )

    return api_response(
        data={"session_id": session_id},
        message="Session deleted successfully.",
    )


@app.errorhandler(RequestEntityTooLarge)
def handle_large_upload(error: RequestEntityTooLarge):
    return api_response(
        message="Uploaded content exceeds the 25 MB MVP limit.",
        status_code=413,
    )


@app.errorhandler(HTTPException)
def handle_http_exception(error: HTTPException):
    return api_response(
        message=error.description,
        status_code=error.code or 500,
    )


@app.errorhandler(ValueError)
def handle_value_error(error: ValueError):
    return api_response(
        message=str(error),
        status_code=400,
    )


@app.errorhandler(PermissionError)
def handle_permission_error(error: PermissionError):
    return api_response(
        message=str(error),
        status_code=403,
    )


@app.errorhandler(InvalidRepositoryURLError)
@app.errorhandler(InvalidRevisionError)
@app.errorhandler(InvalidIncidentFileError)
@app.errorhandler(InvalidIncidentMemoryError)
@app.errorhandler(InvalidTestTargetError)
def handle_bad_request(error: Exception):
    return api_response(
        message=str(error),
        status_code=400,
    )


@app.errorhandler(InvalidSessionStateError)
def handle_invalid_session_state(error: InvalidSessionStateError):
    return api_response(
        message=str(error),
        status_code=409,
    )


@app.errorhandler(SessionNotFoundError)
@app.errorhandler(RepositoryNotFoundError)
def handle_not_found(error: Exception):
    return api_response(
        message=str(error),
        status_code=404,
    )


@app.errorhandler(ReplayTimeoutError)
def handle_replay_timeout(error: ReplayTimeoutError):
    return api_response(
        message=str(error),
        status_code=408,
    )


@app.errorhandler(BobTimeoutError)
def handle_bob_timeout(error: BobTimeoutError):
    return api_response(
        message=str(error),
        status_code=504,
    )


@app.errorhandler(BobShellNotFoundError)
def handle_bob_not_found(error: BobShellNotFoundError):
    return api_response(
        message=str(error),
        status_code=503,
    )


@app.errorhandler(BobExecutionError)
@app.errorhandler(BobOutputError)
def handle_bob_execution_error(error: Exception):
    return api_response(
        message=str(error),
        status_code=502,
    )


@app.errorhandler(BobRunnerError)
def handle_bob_runner_error(error: BobRunnerError):
    return api_response(
        message=str(error),
        status_code=500,
    )


@app.errorhandler(RepositoryCloneError)
@app.errorhandler(ZipExtractionError)
@app.errorhandler(RepositoryManagerError)
@app.errorhandler(IncidentManagerError)
@app.errorhandler(ReplayEngineError)
@app.errorhandler(OrchestratorError)
def handle_norepeat_error(error: Exception):
    return api_response(
        message=str(error),
        status_code=500,
    )


@app.errorhandler(Exception)
def handle_unexpected_error(error: Exception):
    app.logger.exception("Unexpected NoRepeat API error.")
    return api_response(
        message="An unexpected internal error occurred.",
        status_code=500,
    )


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", "5000")),
        debug=os.getenv("FLASK_DEBUG", "0") == "1",
    )
