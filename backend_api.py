from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request
from werkzeug.exceptions import RequestEntityTooLarge

from core.incident_manager import (
    IncidentManagerError,
    InvalidIncidentFileError,
    SessionNotFoundError,
)
from core.orchestrator import (
    InvalidSessionStateError,
    OrchestratorError,
    attach_uploaded_incident,
    create_session_from_github,
    create_session_from_zip,
    delete_session,
    generate_proof_of_non_recurrence,
    get_session_status,
    replay_incident,
    run_baseline,
    verify_after_fix,
)
from core.repository_manager import (
    InvalidRepositoryURLError,
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

# Maximum HTTP upload size for the MVP.
# This covers ZIP projects and incident reports.
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024  # 25 MB


def api_response(
    data: Any = None,
    message: str | None = None,
    status_code: int = 200,
):
    """
    Return a consistent JSON response.

    Response format:
        {
            "success": true,
            "message": "...",
            "data": {}
        }
    """
    payload = {
        "success": status_code < 400,
        "message": message,
        "data": data,
    }

    return jsonify(payload), status_code


def get_json_body() -> dict:
    """
    Return and validate a JSON request body.
    """
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


@app.get("/api/health")
def health():
    """
    Basic API health check.
    """
    return api_response(
        data={
            "service": "NoRepeat API",
            "status": "healthy",
        },
        message="NoRepeat backend is running.",
    )


@app.post("/api/sessions/github")
def create_github_session():
    """
    Create a NoRepeat session from a public GitHub repository.

    Expected JSON:
        {
            "repository_url":
                "https://github.com/owner/repository"
        }
    """
    body = get_json_body()

    repository_url = body.get("repository_url")

    if not isinstance(repository_url, str):
        return api_response(
            message="repository_url is required.",
            status_code=400,
        )

    manifest = create_session_from_github(
        repository_url=repository_url,
    )

    return api_response(
        data=manifest,
        message="GitHub repository loaded successfully.",
        status_code=201,
    )


@app.post("/api/sessions/zip")
def create_zip_session():
    """
    Create a NoRepeat session from an uploaded ZIP project.

    Multipart form:
        project: project.zip
    """
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
            message="ZIP project loaded successfully.",
            status_code=201,
        )

    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink(missing_ok=True)


@app.post("/api/sessions/<session_id>/incident")
def upload_incident(session_id: str):
    """
    Attach an incident report to an existing session.

    Multipart form:
        incident: INC-042.md
    """
    uploaded_file = request.files.get("incident")

    if uploaded_file is None:
        return api_response(
            message="Incident report upload is required.",
            status_code=400,
        )

    filename = uploaded_file.filename or ""

    if not filename:
        return api_response(
            message="Incident filename is required.",
            status_code=400,
        )

    content = uploaded_file.read()

    manifest = attach_uploaded_incident(
        session_id=session_id,
        filename=filename,
        content=content,
    )

    return api_response(
        data=manifest,
        message="Incident report attached successfully.",
    )


@app.post("/api/sessions/<session_id>/baseline")
def baseline(session_id: str):
    """
    Run the repository's existing tests.

    Desired MVP result:
        Existing test suite → PASS
    """
    result = run_baseline(
        session_id=session_id,
    )

    return api_response(
        data=result,
        message="Baseline test suite completed.",
    )


@app.post("/api/sessions/<session_id>/replay")
def incident_replay(session_id: str):
    """
    Run the regression test associated with an incident.

    Expected JSON:
        {
            "incident_test_path":
                "tests/generated/test_INC_042.py"
        }
    """
    body = get_json_body()

    incident_test_path = body.get(
        "incident_test_path"
    )

    if not isinstance(
        incident_test_path,
        str,
    ) or not incident_test_path.strip():
        return api_response(
            message="incident_test_path is required.",
            status_code=400,
        )

    result = replay_incident(
        session_id=session_id,
        incident_test_path=incident_test_path,
    )

    return api_response(
        data=result,
        message=(
            "Incident replay completed. "
            "Review incident_reproduced for the result."
        ),
    )


@app.post("/api/sessions/<session_id>/verify")
def verify(session_id: str):
    """
    Verify the project after a remediation has been applied.

    Expected JSON:
        {
            "incident_test_path":
                "tests/generated/test_INC_042.py"
        }
    """
    body = get_json_body()

    incident_test_path = body.get(
        "incident_test_path"
    )

    if not isinstance(
        incident_test_path,
        str,
    ) or not incident_test_path.strip():
        return api_response(
            message="incident_test_path is required.",
            status_code=400,
        )

    result = verify_after_fix(
        session_id=session_id,
        incident_test_path=incident_test_path,
    )

    return api_response(
        data=result,
        message="Post-fix verification completed.",
    )


@app.post("/api/sessions/<session_id>/proof")
def generate_proof(session_id: str):
    """
    Generate the final Proof of Non-Recurrence.
    """
    proof = generate_proof_of_non_recurrence(
        session_id=session_id,
    )

    return api_response(
        data=proof,
        message="Proof of Non-Recurrence generated.",
    )


@app.get("/api/sessions/<session_id>")
def session_status(session_id: str):
    """
    Return the current state of a NoRepeat session.
    """
    status = get_session_status(
        session_id=session_id,
    )

    return api_response(
        data=status,
        message="Session status retrieved.",
    )


@app.delete("/api/sessions/<session_id>")
def remove_session(session_id: str):
    """
    Delete a NoRepeat analysis session.
    """
    removed = delete_session(
        session_id=session_id,
    )

    if not removed:
        return api_response(
            message="Session was not found.",
            status_code=404,
        )

    return api_response(
        data={
            "session_id": session_id,
        },
        message="Session deleted successfully.",
    )


@app.errorhandler(RequestEntityTooLarge)
def handle_large_upload(
    error: RequestEntityTooLarge,
):
    """
    Handle uploads larger than MAX_CONTENT_LENGTH.
    """
    return api_response(
        message=(
            "Uploaded content exceeds the "
            "25 MB MVP limit."
        ),
        status_code=413,
    )


@app.errorhandler(ValueError)
def handle_value_error(
    error: ValueError,
):
    return api_response(
        message=str(error),
        status_code=400,
    )


@app.errorhandler(
    InvalidRepositoryURLError
)
def handle_invalid_repository_url(
    error: InvalidRepositoryURLError,
):
    return api_response(
        message=str(error),
        status_code=400,
    )


@app.errorhandler(
    InvalidIncidentFileError
)
def handle_invalid_incident(
    error: InvalidIncidentFileError,
):
    return api_response(
        message=str(error),
        status_code=400,
    )


@app.errorhandler(
    InvalidTestTargetError
)
def handle_invalid_test_target(
    error: InvalidTestTargetError,
):
    return api_response(
        message=str(error),
        status_code=400,
    )


@app.errorhandler(
    InvalidSessionStateError
)
def handle_invalid_session_state(
    error: InvalidSessionStateError,
):
    return api_response(
        message=str(error),
        status_code=409,
    )


@app.errorhandler(
    SessionNotFoundError
)
def handle_missing_session(
    error: SessionNotFoundError,
):
    return api_response(
        message=str(error),
        status_code=404,
    )


@app.errorhandler(
    RepositoryNotFoundError
)
def handle_missing_repository(
    error: RepositoryNotFoundError,
):
    return api_response(
        message=str(error),
        status_code=404,
    )


@app.errorhandler(
    ReplayTimeoutError
)
def handle_replay_timeout(
    error: ReplayTimeoutError,
):
    return api_response(
        message=str(error),
        status_code=408,
    )


@app.errorhandler(RepositoryCloneError)
@app.errorhandler(ZipExtractionError)
@app.errorhandler(RepositoryManagerError)
@app.errorhandler(IncidentManagerError)
@app.errorhandler(ReplayEngineError)
@app.errorhandler(OrchestratorError)
def handle_norepeat_error(error: Exception):
    """
    Handle expected NoRepeat internal errors.
    """
    return api_response(
        message=str(error),
        status_code=500,
    )
@app.errorhandler(Exception)
def handle_unexpected_error(
    error: Exception,
):
    """
    Avoid exposing Python stack traces through the API.
    """
    app.logger.exception(
        "Unexpected NoRepeat API error."
    )

    return api_response(
        message="An unexpected internal error occurred.",
        status_code=500,
    )


if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True,
    )