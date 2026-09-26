from __future__ import annotations
from textwrap import dedent

import os
from typing import Any

import requests
import streamlit as st


API_BASE_URL = os.getenv(
    "NOREPEAT_API_URL",
    "http://127.0.0.1:5000",
)

REQUEST_TIMEOUT = 120


# ---------------------------------------------------------------------
# Streamlit configuration
# ---------------------------------------------------------------------

st.set_page_config(
    page_title="NoRepeat",
    page_icon="🔎",
    layout="wide",
)
st.markdown(
    """
    <style>

    /* =========================================================
       BOB AUDITOR THEME — NoRepeat
       Identidad visual: morado brillante + negro, con acentos
       dorados de "sello de auditoría" y tipografía IBM Plex,
       la familia tipográfica oficial de IBM.
       ========================================================= */

    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600;700&family=IBM+Plex+Sans:wght@400;500;600;700;800&display=swap');

    /* ---------------------------------------------------------
       GLOBAL
       --------------------------------------------------------- */

    :root {
        --nr-bg: #050308;
        --nr-panel: #0C0812;
        --nr-panel-soft: #140E1E;
        --nr-border: #2A2038;
        --nr-border-strong: #46316B;

        --nr-purple: #A855F7;
        --nr-purple-deep: #7C3AED;
        --nr-purple-soft: #CBA6FF;
        --nr-purple-dim: rgba(168, 85, 247, 0.14);
        --nr-magenta: #E048A6;

        --nr-gold: #F1C21B;
        --nr-gold-soft: #FFE28A;

        --nr-green: #3DD68C;
        --nr-red: #FF5C7A;
        --nr-yellow: #F1C21B;

        --nr-text: #F5F1FB;
        --nr-muted: #9C90B3;

        --nr-font-sans: 'IBM Plex Sans', -apple-system, BlinkMacSystemFont, sans-serif;
        --nr-font-mono: 'IBM Plex Mono', 'SFMono-Regular', Consolas, monospace;
    }


    html, body, [class^="st-"], [class*=" st-"] {
        font-family: var(--nr-font-sans);
    }


    [data-testid="stAppViewContainer"] {
        background:
            radial-gradient(
                circle at 78% -4%,
                rgba(168, 85, 247, 0.16),
                transparent 32%
            ),
            radial-gradient(
                circle at 6% 18%,
                rgba(224, 72, 166, 0.08),
                transparent 28%
            ),
            var(--nr-bg);
        color: var(--nr-text);
        font-family: var(--nr-font-sans);
    }


    [data-testid="stHeader"] {
        background: rgba(5, 3, 8, 0.85);
        backdrop-filter: blur(10px);
        border-bottom: 1px solid var(--nr-border);
    }


    .block-container {
        max-width: 1180px;
        padding-top: 2rem;
        padding-bottom: 4rem;
    }


    a { color: var(--nr-purple-soft); }
    a:hover { color: var(--nr-purple); }


    /* ---------------------------------------------------------
       SIDEBAR
       --------------------------------------------------------- */

    [data-testid="stSidebar"] {
        background:
            linear-gradient(
                180deg,
                #0E0816 0%,
                #060309 100%
            );

        border-right: 1px solid var(--nr-border);
    }

    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3 {
        font-family: var(--nr-font-mono);
        text-transform: uppercase;
        letter-spacing: 0.08em;
        font-size: 15px;
        color: var(--nr-purple-soft);
    }


    /* ---------------------------------------------------------
       HERO
       --------------------------------------------------------- */

    .nr-hero {
        position: relative;
        overflow: hidden;

        padding: 40px 44px;
        margin-bottom: 22px;

        border: 1px solid var(--nr-border-strong);
        border-radius: 18px;

        background:
            linear-gradient(
                135deg,
                rgba(40, 20, 58, 0.92),
                rgba(8, 5, 12, 0.98)
            );

        box-shadow:
            0 25px 60px rgba(0, 0, 0, 0.45);
    }


    .nr-hero::after {
        content: "";
        position: absolute;

        width: 380px;
        height: 380px;

        right: -140px;
        top: -190px;

        background: var(--nr-purple);
        opacity: 0.16;

        border-radius: 50%;
        filter: blur(30px);
    }


    .nr-hero::before {
        content: "";
        position: absolute;

        width: 260px;
        height: 260px;

        left: -100px;
        bottom: -140px;

        background: var(--nr-magenta);
        opacity: 0.10;

        border-radius: 50%;
        filter: blur(35px);
    }


    .nr-stamp {
        position: absolute;
        top: 30px;
        right: 44px;

        width: 112px;
        height: 112px;

        display: flex;
        align-items: center;
        justify-content: center;

        border: 2px dashed var(--nr-gold);
        border-radius: 50%;

        transform: rotate(-14deg);

        color: var(--nr-gold-soft);

        font-family: var(--nr-font-mono);
        font-size: 10.5px;
        font-weight: 700;
        letter-spacing: 0.05em;
        line-height: 1.45;
        text-align: center;
        text-transform: uppercase;

        opacity: 0.9;
    }


    .nr-badge {
        position: relative;
        z-index: 1;

        display: inline-flex;
        align-items: center;

        gap: 7px;

        padding: 7px 12px;

        border: 1px solid rgba(168, 85, 247, 0.4);
        border-radius: 999px;

        background: var(--nr-purple-dim);

        color: var(--nr-purple-soft);

        font-family: var(--nr-font-mono);
        font-size: 12px;
        letter-spacing: 0.08em;
        text-transform: uppercase;
    }


    .nr-live-dot {
        width: 7px;
        height: 7px;

        border-radius: 50%;
        background: var(--nr-green);

        box-shadow:
            0 0 8px rgba(61, 214, 140, 0.85);
    }


    .nr-title {
        position: relative;
        z-index: 1;

        margin-top: 18px;
        margin-bottom: 4px;

        font-size: 48px;
        line-height: 1.05;

        font-weight: 800;
        letter-spacing: -0.035em;

        color: #FFFFFF;
    }


    .nr-title span {
        background: linear-gradient(90deg, var(--nr-purple-soft), var(--nr-magenta));
        -webkit-background-clip: text;
        background-clip: text;
        color: transparent;
    }


    .nr-tagline {
        position: relative;
        z-index: 1;

        margin-top: 13px;

        max-width: 720px;

        color: #D6CCE6;

        font-size: 18px;
        line-height: 1.55;
    }


    .nr-tagline strong {
        color: #FFFFFF;
    }


    .nr-techline {
        position: relative;
        z-index: 1;

        margin-top: 21px;

        color: var(--nr-purple-soft);

        font-family: var(--nr-font-mono);
        font-size: 13px;
    }


    /* ---------------------------------------------------------
       VALUE CARDS
       --------------------------------------------------------- */

    .nr-card-grid {
        display: grid;
        grid-template-columns: repeat(3, 1fr);

        gap: 14px;

        margin-top: 20px;
        margin-bottom: 27px;
    }


    .nr-card {
        position: relative;

        min-height: 145px;

        padding: 21px;

        background:
            linear-gradient(
                150deg,
                rgba(24, 15, 34, 0.95),
                rgba(8, 5, 12, 0.97)
            );

        border: 1px solid var(--nr-border);
        border-radius: 14px;

        transition: border-color 0.15s ease, transform 0.15s ease;
    }


    .nr-card:hover {
        border-color: var(--nr-border-strong);
        transform: translateY(-2px);
    }


    /* evidence-tag corner marks */
    .nr-card::before,
    .nr-card::after {
        content: "";
        position: absolute;

        width: 13px;
        height: 13px;

        border-color: var(--nr-purple-soft);
        opacity: 0.5;
    }

    .nr-card::before {
        top: 8px;
        left: 8px;

        border-top: 2px solid;
        border-left: 2px solid;
    }

    .nr-card::after {
        bottom: 8px;
        right: 8px;

        border-bottom: 2px solid;
        border-right: 2px solid;
    }


    .nr-card-number {
        margin-bottom: 13px;

        color: var(--nr-purple-soft);

        font-family: var(--nr-font-mono);
        font-size: 12px;

        text-transform: uppercase;
        letter-spacing: 0.1em;
    }


    .nr-card-title {
        color: #FFFFFF;

        font-size: 17px;
        font-weight: 650;

        margin-bottom: 7px;
    }


    .nr-card-description {
        color: #B8ACC9;

        font-size: 13px;
        line-height: 1.55;
    }


    /* ---------------------------------------------------------
       AUDIT PIPELINE
       --------------------------------------------------------- */

    .nr-pipeline {
        display: grid;

        grid-template-columns:
            1fr auto
            1fr auto
            1fr auto
            1fr;

        align-items: center;

        gap: 8px;

        margin-bottom: 32px;
        padding: 18px;

        border: 1px solid var(--nr-border);
        border-radius: 14px;

        background: rgba(12, 8, 18, 0.8);
    }


    .nr-stage {
        text-align: center;

        padding: 12px 6px;
    }


    .nr-stage-id {
        color: var(--nr-purple-soft);

        font-family: var(--nr-font-mono);
        font-size: 11px;

        text-transform: uppercase;
    }


    .nr-stage-name {
        margin-top: 4px;

        color: #FFFFFF;

        font-size: 14px;
        font-weight: 600;
    }


    .nr-stage-detail {
        margin-top: 3px;

        color: #8A7D9E;

        font-size: 11px;
    }


    .nr-arrow {
        color: var(--nr-border-strong);
        font-size: 20px;
    }


    /* ---------------------------------------------------------
       SECTION HEADER
       --------------------------------------------------------- */

    .nr-section-label {
        color: var(--nr-purple-soft);

        font-family: var(--nr-font-mono);
        font-size: 12px;

        letter-spacing: 0.12em;
        text-transform: uppercase;

        margin-bottom: 4px;
    }

    .nr-section-label::before {
        content: "§ ";
        color: var(--nr-gold);
    }


    .nr-section-title {
        color: #FFFFFF;

        font-size: 28px;
        font-weight: 700;

        margin-bottom: 7px;
    }


    .nr-section-description {
        color: var(--nr-muted);

        font-size: 14px;

        margin-bottom: 22px;
    }


    /* ---------------------------------------------------------
       AUDITOR TERMINAL
       --------------------------------------------------------- */

    .nr-auditor-box {
        border: 1px solid var(--nr-border-strong);
        border-radius: 14px;

        overflow: hidden;

        background: #08050C;

        margin: 18px 0 24px 0;

        box-shadow: 0 0 0 1px rgba(168, 85, 247, 0.06);
    }


    .nr-auditor-header {
        display: flex;
        justify-content: space-between;
        align-items: center;

        padding: 11px 16px;

        border-bottom: 1px solid var(--nr-border);

        background: #140B20;

        font-family: var(--nr-font-mono);
        font-size: 12px;
        letter-spacing: 0.04em;

        color: var(--nr-purple-soft);
    }


    .nr-auditor-body {
        padding: 18px;

        color: #B8ACC9;

        font-family: var(--nr-font-mono);
        font-size: 12px;
        line-height: 1.8;
    }


    .nr-command {
        color: var(--nr-gold);
    }


    .nr-muted {
        color: #625A73;
    }


    /* ---------------------------------------------------------
       BUTTONS
       --------------------------------------------------------- */

    .stButton > button {
        min-height: 42px;

        border: 1px solid var(--nr-purple);
        border-radius: 8px;

        background:
            linear-gradient(
                135deg,
                #7C3AED,
                #A855F7
            );

        color: white;

        font-weight: 650;
        font-family: var(--nr-font-sans);

        box-shadow:
            0 7px 20px rgba(124, 58, 237, 0.22);

        transition:
            transform 0.15s ease,
            box-shadow 0.15s ease,
            border-color 0.15s ease;
    }


    .stButton > button:hover {
        transform: translateY(-1px);

        border-color: var(--nr-purple-soft);

        box-shadow:
            0 10px 28px rgba(168, 85, 247, 0.32);
    }


    .stButton > button:focus {
        box-shadow: 0 0 0 2px rgba(168, 85, 247, 0.35);
    }


    /* ---------------------------------------------------------
       INPUTS
       --------------------------------------------------------- */

    [data-testid="stTextInput"] input {
        background: var(--nr-panel);
        border: 1px solid var(--nr-border-strong);

        color: #FFFFFF;
    }

    [data-testid="stTextInput"] input:focus {
        border-color: var(--nr-purple);
        box-shadow: 0 0 0 1px rgba(168, 85, 247, 0.35);
    }


    [data-testid="stFileUploaderDropzone"] {
        background: var(--nr-panel);

        border: 1px dashed var(--nr-border-strong);
        border-radius: 10px;
    }


    /* Streamlit renders radio/checkbox/slider through its internal
       BaseWeb components, not plain <input> elements, so the visible
       dot/thumb ignores accent-color. Target the BaseWeb markers
       directly so the selected state matches the BOB purple instead
       of Streamlit's default red. */

    [data-testid="stRadio"] input[type="radio"],
    [data-testid="stCheckbox"] input[type="checkbox"] {
        accent-color: var(--nr-purple);
    }

    [data-baseweb="radio"] > div:first-of-type {
        border-color: var(--nr-border-strong) !important;
    }

    [data-baseweb="radio"] input:checked + div,
    [data-baseweb="radio"] > div:first-of-type:has(input:checked) {
        border-color: var(--nr-purple) !important;
    }

    [data-baseweb="radio"] > div:first-of-type > div {
        background: var(--nr-purple) !important;
    }

    [data-baseweb="checkbox"] > div:first-of-type {
        border-color: var(--nr-border-strong) !important;
        background: var(--nr-panel) !important;
    }

    [data-baseweb="checkbox"] input:checked ~ div:first-of-type {
        background: var(--nr-purple) !important;
        border-color: var(--nr-purple) !important;
    }

    [data-baseweb="slider"] div[role="slider"] {
        background: var(--nr-purple) !important;
        border-color: var(--nr-purple) !important;
    }

    [data-baseweb="slider"] > div > div:nth-child(2) {
        background: var(--nr-purple) !important;
    }

    [data-testid="stSpinner"] svg {
        color: var(--nr-purple) !important;
    }


    /* ---------------------------------------------------------
       METRICS
       --------------------------------------------------------- */

    [data-testid="stMetric"] {
        padding: 14px;

        background: var(--nr-panel);

        border: 1px solid var(--nr-border);
        border-radius: 10px;
    }

    [data-testid="stMetricLabel"] {
        color: var(--nr-muted);
    }


    /* ---------------------------------------------------------
       ALERTS, EXPANDERS, CODE, JSON, DIVIDERS
       --------------------------------------------------------- */

    [data-testid="stAlert"] {
        background: var(--nr-panel-soft);
        border: 1px solid var(--nr-border);
        border-radius: 10px;
    }


    [data-testid="stExpander"] {
        background: var(--nr-panel);
        border: 1px solid var(--nr-border);
        border-radius: 10px;
    }


    [data-testid="stCodeBlock"] {
        border: 1px solid var(--nr-border);
        border-radius: 10px;
    }


    [data-testid="stJson"] {
        background: var(--nr-panel);
        border: 1px solid var(--nr-border-strong);
        border-radius: 10px;
    }


    hr {
        border-color: var(--nr-border) !important;
    }


    /* ---------------------------------------------------------
       RESPONSIVE
       --------------------------------------------------------- */

    @media (max-width: 850px) {

        .nr-card-grid {
            grid-template-columns: 1fr;
        }

        .nr-pipeline {
            grid-template-columns: 1fr;
        }

        .nr-arrow {
            transform: rotate(90deg);
        }

        .nr-title {
            font-size: 38px;
        }

        .nr-stamp {
            display: none;
        }

    }


    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------

DEFAULT_STATE = {
    "session_id": None,
    "session_status": None,
    "repository_loaded": False,
    "incident_loaded": False,
    "baseline_result": None,
    "replay_result": None,
    "verification_result": None,
    "proof_result": None,
}


for key, default_value in DEFAULT_STATE.items():
    if key not in st.session_state:
        st.session_state[key] = default_value


# ---------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------

def api_request(
    method: str,
    endpoint: str,
    **kwargs: Any,
) -> dict | None:
    """
    Send a request to the NoRepeat backend API.

    Returns:
        Parsed JSON response or None when communication fails.
    """
    url = f"{API_BASE_URL}{endpoint}"

    try:
        response = requests.request(
            method=method,
            url=url,
            timeout=REQUEST_TIMEOUT,
            **kwargs,
        )

    except requests.exceptions.ConnectionError:
        st.error(
            "Unable to connect to the NoRepeat backend. "
            "Make sure backend_api.py is running on port 5000."
        )
        return None

    except requests.exceptions.Timeout:
        st.error(
            "The NoRepeat backend request timed out."
        )
        return None

    except requests.exceptions.RequestException as exc:
        st.error(
            f"Backend communication error: {exc}"
        )
        return None

    try:
        payload = response.json()

    except ValueError:
        st.error(
            "The backend returned an invalid JSON response."
        )
        return None

    if not response.ok or not payload.get("success", False):
        message = payload.get(
            "message",
            "The backend operation failed.",
        )

        st.error(message)
        return None

    return payload


def check_backend_health() -> bool:
    """Return True when the NoRepeat backend is reachable."""
    payload = api_request(
        "GET",
        "/api/health",
    )

    return bool(
        payload
        and payload.get("data", {}).get("status") == "healthy"
    )


def refresh_session_status() -> dict | None:
    """Refresh the current NoRepeat session state."""
    session_id = st.session_state.session_id

    if not session_id:
        return None

    payload = api_request(
        "GET",
        f"/api/sessions/{session_id}",
    )

    if payload:
        st.session_state.session_status = payload["data"]

    return payload


def reset_local_state() -> None:
    """Reset the local Streamlit state."""
    for key, default_value in DEFAULT_STATE.items():
        st.session_state[key] = default_value


# ---------------------------------------------------------------------
# Presentation helpers
# ---------------------------------------------------------------------

def show_pytest_result(
    title: str,
    result: dict | None,
) -> None:
    """Display a structured pytest result."""
    if not result:
        return

    status = result.get(
        "status",
        "UNKNOWN",
    )

    results = result.get(
        "results",
        {},
    )

    passed = results.get("passed", 0)
    failed = results.get("failed", 0)
    errors = results.get("errors", 0)
    skipped = results.get("skipped", 0)

    st.subheader(title)

    col1, col2, col3, col4 = st.columns(4)

    col1.metric(
        "Passed",
        passed,
    )

    col2.metric(
        "Failed",
        failed,
    )

    col3.metric(
        "Errors",
        errors,
    )

    col4.metric(
        "Skipped",
        skipped,
    )

    if status == "PASS":
        st.success("Test execution passed.")
    elif status == "FAIL":
        st.error("Test execution failed.")
    else:
        st.warning(
            f"Test execution status: {status}"
        )

    with st.expander(
        "View pytest output"
    ):
        stdout = result.get(
            "stdout",
            "",
        )

        stderr = result.get(
            "stderr",
            "",
        )

        if stdout:
            st.code(
                stdout,
                language="text",
            )

        if stderr:
            st.code(
                stderr,
                language="text",
            )


def display_workflow_status() -> None:
    """Display the current NoRepeat workflow progress."""
    status = st.session_state.session_status or {}

    current_status = status.get(
        "status",
        "NOT_STARTED",
    )

    st.subheader("Analysis workflow")

    steps = [
        (
            "Repository",
            bool(status.get("repository")),
        ),
        (
            "Incident report",
            bool(status.get("incident")),
        ),
        (
            "Baseline",
            bool(status.get("baseline_completed")),
        ),
        (
            "Incident replay",
            bool(status.get("incident_replay_completed")),
        ),
        (
            "Verification",
            bool(status.get("verification_completed")),
        ),
        (
            "Proof",
            (
                status.get("proof", {}).get("status")
                == "VERIFIED"
            ),
        ),
    ]

    columns = st.columns(len(steps))

    for column, (name, completed) in zip(
        columns,
        steps,
    ):
        if completed:
            column.success(
                f"✓ {name}"
            )
        else:
            column.info(
                f"○ {name}"
            )

    st.caption(
        f"Current session state: {current_status}"
    )


# ---------------------------------------------------------------------
# Header / Mini landing page
# ---------------------------------------------------------------------

st.markdown(
    dedent(
        """
        <div class="nr-hero">
            <div class="nr-stamp">
                Bob<br>Auditor<br>Certified
            </div>
            <div class="nr-badge">
                <span class="nr-live-dot"></span>
                AUDIT SESSION · ACTIVE
            </div>
            <div class="nr-title">
                No<span>Repeat</span>
            </div>
            <div class="nr-tagline">
                <strong>Incident Replay &amp; Proof of Non-Recurrence</strong>,
                powered by IBM Bob 2.0. Bob audits the historical incident,
                proves the failure and certifies that it does not repeat.
            </div>
            <div class="nr-techline">
                $ bob --mode auditor --workspace ./norepeat_mvp --case INC-042
            </div>
        </div>
        """
    ),
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="nr-card-grid">
        <div class="nr-card">
            <div class="nr-card-number">01 / REMEMBER</div>
            <div class="nr-card-title">Turn incidents into memory</div>
            <div class="nr-card-description">
                NoRepeat connects engineering postmortems with the current
                source code so lessons do not remain trapped in documentation.
            </div>
        </div>
        <div class="nr-card">
            <div class="nr-card-number">02 / REPLAY</div>
            <div class="nr-card-title">Prove the failure</div>
            <div class="nr-card-description">
                IBM Bob correlates historical root cause with the codebase
                and creates regression evidence that proves whether the
                incident can recur.
            </div>
        </div>
        <div class="nr-card">
            <div class="nr-card-number">03 / PROTECT</div>
            <div class="nr-card-title">Verify remediation</div>
            <div class="nr-card-description">
                Bob applies the smallest justified fix and NoRepeat verifies
                that the known incident scenario no longer reproduces.
            </div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="nr-pipeline">
        <div class="nr-stage">
            <div class="nr-stage-id">STEP 01</div>
            <div class="nr-stage-name">Understand</div>
            <div class="nr-stage-detail">Incident history</div>
        </div>
        <div class="nr-arrow">→</div>
        <div class="nr-stage">
            <div class="nr-stage-id">STEP 02</div>
            <div class="nr-stage-name">Replay</div>
            <div class="nr-stage-detail">Reproduce failure</div>
        </div>
        <div class="nr-arrow">→</div>
        <div class="nr-stage">
            <div class="nr-stage-id">STEP 03</div>
            <div class="nr-stage-name">Remediate</div>
            <div class="nr-stage-detail">IBM Bob fix</div>
        </div>
        <div class="nr-arrow">→</div>
        <div class="nr-stage">
            <div class="nr-stage-id">STEP 04</div>
            <div class="nr-stage-name">Verify</div>
            <div class="nr-stage-detail">Non-recurrence proof</div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="nr-section-label">AUDIT CONSOLE</div>
    <div class="nr-section-title">Start an incident audit</div>
    <div class="nr-section-description">
        Provide the current application and the historical incident
        that NoRepeat should investigate.
    </div>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------
# Backend status
# ---------------------------------------------------------------------

with st.sidebar:
    st.header("System")

    backend_healthy = check_backend_health()

    if backend_healthy:
        st.success(
            "Backend connected"
        )
    else:
        st.error(
            "Backend unavailable"
        )

    st.caption(
        API_BASE_URL
    )

    if st.session_state.session_id:
        st.divider()

        st.caption(
            "Current session"
        )

        st.code(
            st.session_state.session_id,
            language="text",
        )

        if st.button(
            "Refresh session",
            use_container_width=True,
        ):
            refresh_session_status()
            st.rerun()

        if st.button(
            "Delete session",
            use_container_width=True,
        ):
            payload = api_request(
                "DELETE",
                (
                    "/api/sessions/"
                    f"{st.session_state.session_id}"
                ),
            )

            if payload:
                reset_local_state()

                st.success(
                    "Session deleted."
                )

                st.rerun()


# ---------------------------------------------------------------------
# Step 1 - Repository
# ---------------------------------------------------------------------

st.markdown(
    """
    <div class="nr-section-label">STEP 01 · APPLICATION SOURCE</div>
    <div class="nr-section-title">Select the application</div>
    <div class="nr-section-description">
        Load the codebase that will be correlated with the historical incident.
        For the hackathon demo, use the controlled public demo repository.
    </div>
    """,
    unsafe_allow_html=True,
)

repository_source = st.radio(
    "Project source",
    [
        "GitHub repository",
        "ZIP upload",
    ],
    horizontal=True,
)


if repository_source == "GitHub repository":
    repository_url = st.text_input(
        "Public GitHub repository URL",
        placeholder=(
            "https://github.com/"
            "your-team/norepeat-demo-app"
        ),
    )

    if st.button(
        "Load GitHub repository",
        type="primary",
    ):
        if not repository_url.strip():
            st.warning(
                "Enter a GitHub repository URL."
            )

        else:
            with st.spinner(
                "Cloning repository..."
            ):
                payload = api_request(
                    "POST",
                    "/api/sessions/github",
                    json={
                        "repository_url":
                            repository_url.strip(),
                    },
                )

            if payload:
                manifest = payload["data"]

                st.session_state.session_id = (
                    manifest["session_id"]
                )

                st.session_state.repository_loaded = True
                st.session_state.session_status = manifest

                st.success(
                    "Repository loaded successfully."
                )

                st.rerun()


else:
    uploaded_zip = st.file_uploader(
        "Upload project ZIP",
        type=["zip"],
        key="project_zip",
    )

    if st.button(
        "Load ZIP project",
        type="primary",
    ):
        if uploaded_zip is None:
            st.warning(
                "Select a ZIP project first."
            )

        else:
            with st.spinner(
                "Preparing project workspace..."
            ):
                payload = api_request(
                    "POST",
                    "/api/sessions/zip",
                    files={
                        "project": (
                            uploaded_zip.name,
                            uploaded_zip.getvalue(),
                            "application/zip",
                        )
                    },
                )

            if payload:
                manifest = payload["data"]

                st.session_state.session_id = (
                    manifest["session_id"]
                )

                st.session_state.repository_loaded = True
                st.session_state.session_status = manifest

                st.success(
                    "ZIP project loaded successfully."
                )

                st.rerun()


# ---------------------------------------------------------------------
# Remaining workflow requires a repository
# ---------------------------------------------------------------------

if not st.session_state.session_id:
    st.info(
        "Load a repository to begin a NoRepeat analysis session."
    )

    st.stop()


refresh_session_status()

display_workflow_status()

st.divider()


# ---------------------------------------------------------------------
# Step 2 - Incident report
# ---------------------------------------------------------------------

st.markdown(
    """
    <div class="nr-section-label">STEP 02 · HISTORICAL EVIDENCE</div>
    <div class="nr-section-title">Attach the historical incident</div>
    <div class="nr-section-description">
        Upload the postmortem or incident report describing a failure
        that previously affected this application.
    </div>
    """,
    unsafe_allow_html=True,
)

incident_file = st.file_uploader(
    "Incident report",
    type=[
        "md",
        "txt",
    ],
    key="incident_report",
)

if st.button(
    "Attach incident report"
):
    if incident_file is None:
        st.warning(
            "Select an incident report first."
        )

    else:
        session_id = st.session_state.session_id

        with st.spinner(
            "Uploading incident report..."
        ):
            payload = api_request(
                "POST",
                (
                    f"/api/sessions/"
                    f"{session_id}/incident"
                ),
                files={
                    "incident": (
                        incident_file.name,
                        incident_file.getvalue(),
                        "text/plain",
                    )
                },
            )

        if payload:
            st.session_state.incident_loaded = True
            st.session_state.session_status = payload["data"]

            st.success(
                "Incident report attached successfully."
            )

            st.rerun()


current_status = st.session_state.session_status or {}

if not current_status.get("incident"):
    st.info(
        "Attach an incident report before continuing."
    )

    st.stop()


st.divider()


# ---------------------------------------------------------------------
# Step 3 - Baseline
# ---------------------------------------------------------------------

st.markdown(
    """
    <div class="nr-section-label">STEP 03 · BASELINE</div>
    <div class="nr-section-title">Establish the project baseline</div>
    <div class="nr-section-description">
        Run the existing test suite before historical incident knowledge
        is applied. The strongest demo starts with a project that appears
        healthy according to its current coverage.
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="nr-auditor-box">
        <div class="nr-auditor-header">
            <span>BASELINE GATE</span>
            <span>DETERMINISTIC · PYTEST</span>
        </div>
        <div class="nr-auditor-body">
            <span class="nr-muted">$</span>
            <span class="nr-command">pytest existing suite</span><br>
            Expected demo state: <strong>PASS</strong><br>
            <span class="nr-muted">
                This proves that the historical failure is missing from
                current regression coverage.
            </span>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

if st.button(
    "Run baseline tests",
    type="primary",
):
    session_id = st.session_state.session_id

    with st.spinner(
        "Running the existing pytest suite..."
    ):
        payload = api_request(
            "POST",
            (
                f"/api/sessions/"
                f"{session_id}/baseline"
            ),
        )

    if payload:
        result = payload["data"]

        st.session_state.baseline_result = result

        refresh_session_status()

        if result.get("success"):
            st.success(
                "Baseline passed."
            )
        else:
            st.warning(
                "Baseline did not pass. "
                "Review the existing project tests "
                "before continuing the demo."
            )


show_pytest_result(
    "Baseline result",
    st.session_state.baseline_result,
)


st.divider()


# ---------------------------------------------------------------------
# Step 4 - IBM Bob
# ---------------------------------------------------------------------

st.markdown(
    """
    <div class="nr-section-label">STEP 04 · BOB AUDITOR</div>
    <div class="nr-section-title">Incident intelligence</div>
    <div class="nr-section-description">
        Bob now takes control of the reasoning phase. Independent analysis
        roles inspect the historical incident, source code and missing
        regression coverage before any remediation.
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="nr-auditor-box">
        <div class="nr-auditor-header">
            <span>BOB AUDITOR CORE</span>
            <span>AGENT MODE · READY</span>
        </div>
        <div class="nr-auditor-body">
            <span class="nr-muted">$</span>
            <span class="nr-command">analyze historical incident</span><br>
            ├── Incident Analyst
            <span class="nr-muted">→ root cause</span><br>
            ├── Codebase Analyst
            <span class="nr-muted">→ affected implementation</span><br>
            ├── Test Analyst
            <span class="nr-muted">→ missing regression coverage</span><br>
            └── Bob Orchestrator
            <span class="nr-muted">→ evidence correlation</span>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
Bob must use the repository and the incident report to:

1. Understand the historical incident.
2. Identify the root cause.
3. Explore the relevant code.
4. Correlate the incident with the current implementation.
5. Design and create a regression test.
6. Reproduce the historical incident **before modifying application code**.
"""
)

st.info(
    "Bob automation will be connected through core/bob_runner.py. "
    "During the current development phase, perform this workflow "
    "directly in IBM Bob IDE."
)

st.caption(
    "Expected Bob-generated test: tests/generated/test_INC_042.py"
)


# ---------------------------------------------------------------------
# Step 5 - Incident replay
# ---------------------------------------------------------------------

st.markdown(
    """
    <div class="nr-section-label">STEP 05 · INCIDENT REPLAY</div>
    <div class="nr-section-title">Replay the historical incident</div>
    <div class="nr-section-description">
        Execute Bob's regression test against the current implementation.
        A failing test is evidence that the historical incident condition
        has been reproduced.
    </div>
    """,
    unsafe_allow_html=True,
)

incident_test_path = st.text_input(
    "Generated regression test path",
    value="tests/generated/test_INC_042.py",
)

if st.button(
    "Run incident replay"
):
    session_id = st.session_state.session_id

    with st.spinner(
        "Replaying historical incident..."
    ):
        payload = api_request(
            "POST",
            (
                f"/api/sessions/"
                f"{session_id}/replay"
            ),
            json={
                "incident_test_path":
                    incident_test_path.strip(),
            },
        )

    if payload:
        replay = payload["data"]

        st.session_state.replay_result = replay

        refresh_session_status()

        if replay.get(
            "incident_reproduced"
        ):
            st.error(
                "Historical incident reproduced."
            )
        else:
            st.warning(
                "The regression test did not reproduce "
                "the historical incident."
            )


if st.session_state.replay_result:
    replay_data = (
        st.session_state.replay_result
    )

    show_pytest_result(
        "Incident replay result",
        replay_data.get("pytest"),
    )


st.divider()


# ---------------------------------------------------------------------
# Step 6 - Bob remediation
# ---------------------------------------------------------------------

st.markdown(
    """
    <div class="nr-section-label">STEP 06 · BOB REMEDIATION</div>
    <div class="nr-section-title">Apply the smallest justified fix</div>
    <div class="nr-section-description">
        After the failure is proven, Bob can remediate the implementation
        without deleting or weakening the evidence that exposed it.
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
Once the historical incident has been reproduced, IBM Bob should:

1. Analyze the failing regression test.
2. Apply the smallest justified remediation.
3. Preserve the regression test.
4. Avoid weakening existing tests.
5. Run the test suite again.
"""
)

st.info(
    "This is the second critical Bob phase. "
    "Do not manually modify the vulnerable code during the official demo."
)


# ---------------------------------------------------------------------
# Step 7 - Verification
# ---------------------------------------------------------------------

st.markdown(
    """
    <div class="nr-section-label">STEP 07 · VERIFICATION</div>
    <div class="nr-section-title">Verify the remediation</div>
    <div class="nr-section-description">
        NoRepeat requires both the historical regression test and the
        original project test suite to pass before verification succeeds.
    </div>
    """,
    unsafe_allow_html=True,
)

if st.button(
    "Verify after fix"
):
    session_id = st.session_state.session_id

    with st.spinner(
        "Verifying remediation..."
    ):
        payload = api_request(
            "POST",
            (
                f"/api/sessions/"
                f"{session_id}/verify"
            ),
            json={
                "incident_test_path":
                    incident_test_path.strip(),
            },
        )

    if payload:
        verification = payload["data"]

        st.session_state.verification_result = (
            verification
        )

        refresh_session_status()

        if verification.get("verified"):
            st.success(
                "Non-recurrence verified for the known incident scenario."
            )
        else:
            st.error(
                "Verification failed."
            )


if st.session_state.verification_result:
    verification = (
        st.session_state.verification_result
    )

    show_pytest_result(
        "Incident regression test",
        verification.get(
            "incident_test"
        ),
    )

    show_pytest_result(
        "Full project test suite",
        verification.get(
            "full_test_suite"
        ),
    )


st.divider()


# ---------------------------------------------------------------------
# Step 8 - Proof of Non-Recurrence
# ---------------------------------------------------------------------

st.markdown(
    """
    <div class="nr-section-label">STEP 08 · AUDIT EVIDENCE</div>
    <div class="nr-section-title">Proof of Non-Recurrence</div>
    <div class="nr-section-description">
        Generate the final evidence package showing that the known
        incident was reproduced before remediation and no longer
        reproduces after remediation.
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
Generate the final structured artifact demonstrating that the known
incident scenario was reproduced before remediation and no longer
reproduces after remediation.
"""
)

if st.button(
    "Generate proof",
    type="primary",
):
    session_id = st.session_state.session_id

    with st.spinner(
        "Generating Proof of Non-Recurrence..."
    ):
        payload = api_request(
            "POST",
            (
                f"/api/sessions/"
                f"{session_id}/proof"
            ),
        )

    if payload:
        proof = payload["data"]

        st.session_state.proof_result = proof

        refresh_session_status()

        if proof.get(
            "non_recurrence_verified"
        ):
            st.success(
                "🛡️ PROTECTED — Proof of Non-Recurrence verified."
            )
        else:
            st.error(
                "Proof could not be verified."
            )


if st.session_state.proof_result:
    proof = st.session_state.proof_result

    st.json(proof)


st.divider()

st.caption(
    "NoRepeat proves non-recurrence only for the historical incident "
    "scenario represented by the generated regression test. "
    "It does not claim that the application is free of all vulnerabilities."
)