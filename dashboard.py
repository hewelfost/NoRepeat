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
BOB_REQUEST_TIMEOUT = 1000
CLEANUP_TOKEN = os.getenv("NOREPEAT_CLEANUP_TOKEN", "").strip()


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


    html, body {
        font-family: var(--nr-font-sans);
        font-size: 16.5px;
    }

    [data-testid="stAppViewContainer"] p,
    [data-testid="stAppViewContainer"] label,
    [data-testid="stAppViewContainer"] input,
    [data-testid="stAppViewContainer"] textarea {
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
        font-size: 16px;
        color: var(--nr-purple-soft);
    }


    [data-testid="stSidebarCollapseButton"] button,
    [data-testid="stSidebarCollapsedControl"] button {
        width: 34px !important;
        min-width: 34px !important;
        height: 34px !important;
        min-height: 34px !important;
        padding: 0 !important;
        border-radius: 8px !important;
        overflow: hidden !important;
    }

    [data-testid="stSidebarCollapseButton"] button span,
    [data-testid="stSidebarCollapsedControl"] button span {
        white-space: nowrap !important;
        overflow: hidden !important;
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

        width: 122px;
        height: 122px;

        display: flex;
        align-items: center;
        justify-content: center;

        padding: 12px;
        border: 2px dashed var(--nr-gold);
        border-radius: 50%;

        background: rgba(16, 9, 26, 0.55);
        backdrop-filter: blur(4px);
        box-shadow: 0 0 0 6px rgba(241, 194, 27, 0.05);
    }

    .nr-stamp img {
        width: 82px;
        height: 82px;
        object-fit: contain;
        border-radius: 22px;
        filter: drop-shadow(0 10px 18px rgba(0, 0, 0, 0.45));
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

        font-size: 56px;
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

        font-size: 21px;
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
        font-size: 15px;
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

        font-size: 19px;
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

        font-size: 16px;
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

        font-size: 34px;
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


    /* ---------------------------------------------------------
       BOB MASCOT — floating auditor companion
       Original character, not a reproduction of any third-party
       logo or artwork; purely decorative interface feedback.
       --------------------------------------------------------- */

    .nr-bob-wrap {
        position: fixed;
        right: 26px;
        bottom: 22px;
        z-index: 999;

        display: flex;
        align-items: flex-end;
        gap: 12px;

        pointer-events: none;
    }


    .nr-bob-bubble {
        max-width: 230px;
        margin-bottom: 16px;

        padding: 10px 14px;

        background: var(--nr-panel-soft);
        border: 1px solid var(--nr-border-strong);
        border-radius: 12px 12px 2px 12px;

        color: var(--nr-text);
        font-family: var(--nr-font-sans);
        font-size: 12.5px;
        line-height: 1.45;

        box-shadow: 0 14px 30px rgba(0, 0, 0, 0.5);
    }


    .nr-bob-bubble .nr-bob-tag {
        display: flex;
        align-items: center;
        gap: 5px;

        margin-bottom: 4px;

        color: var(--nr-purple-soft);

        font-family: var(--nr-font-mono);
        font-size: 10px;
        letter-spacing: 0.1em;
        text-transform: uppercase;
    }


    .nr-bob-dots span {
        display: inline-block;

        width: 4px;
        height: 4px;

        margin-left: 1px;

        border-radius: 50%;
        background: var(--nr-purple-soft);

        animation: nr-bob-dot 1.2s infinite ease-in-out;
    }

    .nr-bob-dots span:nth-child(2) { animation-delay: 0.2s; }
    .nr-bob-dots span:nth-child(3) { animation-delay: 0.4s; }


    .nr-bob-avatar {
        position: relative;

        width: 66px;
        height: 66px;
        flex-shrink: 0;

        display: flex;
        align-items: center;
        justify-content: center;

        background: linear-gradient(150deg, rgba(124, 58, 237, 0.92), rgba(18, 10, 28, 0.96));
        border: 1px solid var(--nr-border-strong);
        border-radius: 50%;

        box-shadow: 0 10px 26px rgba(124, 58, 237, 0.35);

        animation: nr-bob-float 3.2s ease-in-out infinite;
    }


    .nr-bob-avatar svg {
        width: 42px;
        height: 42px;
        display: none;
    }


    .nr-bob-welcome .nr-bob-icon-welcome,
    .nr-bob-investigating .nr-bob-icon-investigating,
    .nr-bob-thinking .nr-bob-icon-thinking,
    .nr-bob-verdict .nr-bob-icon-verdict {
        display: block !important;
    }


    .nr-bob-thinking .nr-bob-avatar {
        animation: nr-bob-float 3.2s ease-in-out infinite, nr-bob-pulse 1.5s ease-in-out infinite;
    }


    @keyframes nr-bob-float {
        0%, 100% { transform: translateY(0); }
        50% { transform: translateY(-6px); }
    }

    @keyframes nr-bob-pulse {
        0%, 100% { box-shadow: 0 10px 26px rgba(124, 58, 237, 0.35); }
        50% { box-shadow: 0 10px 34px rgba(168, 85, 247, 0.65); }
    }

    @keyframes nr-bob-dot {
        0%, 80%, 100% { opacity: 0.25; transform: translateY(0); }
        40% { opacity: 1; transform: translateY(-3px); }
    }


    @media (max-width: 850px) {
        .nr-bob-wrap { right: 14px; bottom: 14px; }
        .nr-bob-bubble { max-width: 168px; font-size: 11.5px; padding: 8px 11px; }
        .nr-bob-avatar { width: 54px; height: 54px; }
        .nr-bob-avatar svg { width: 34px; height: 34px; }
    }




    /* ---------------------------------------------------------
       BOB ASSISTANT PANEL
       --------------------------------------------------------- */

    .nr-bob-panel {
        margin-top: 14px;
        padding: 14px;
        background: linear-gradient(160deg, rgba(20, 14, 30, 0.94), rgba(10, 6, 16, 0.98));
        border: 1px solid var(--nr-border-strong);
        border-radius: 16px;
        box-shadow: 0 14px 32px rgba(0, 0, 0, 0.35);
    }

    .nr-bob-panel-tag {
        margin-bottom: 6px;
        color: var(--nr-purple-soft);
        font-family: var(--nr-font-mono);
        font-size: 11px;
        letter-spacing: 0.12em;
        text-transform: uppercase;
    }

    .nr-bob-panel-title {
        color: #FFFFFF;
        font-size: 19px;
        font-weight: 700;
        margin-bottom: 8px;
    }

    .nr-bob-panel-message {
        color: #E8DCF7;
        font-size: 14.5px;
        line-height: 1.55;
    }

    .nr-bob-panel-layout {
        display: grid;
        grid-template-columns: 74px 1fr;
        gap: 12px;
        align-items: center;
    }

    .nr-bob-avatar-shell {
        position: relative;
        width: 74px;
        height: 74px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        background: radial-gradient(circle at 30% 30%, rgba(255,255,255,0.08), rgba(124, 58, 237, 0.15)), #120A1C;
        border: 1px solid var(--nr-border-strong);
        box-shadow: 0 10px 22px rgba(124, 58, 237, 0.25);
        overflow: visible;
    }

    .nr-bob-avatar-shell img {
        width: 54px;
        height: 54px;
        object-fit: contain;
        border-radius: 16px;
    }

    .nr-bob-mode-emoji {
        position: absolute;
        right: -2px;
        bottom: -4px;
        width: 28px;
        height: 28px;
        display: flex;
        align-items: center;
        justify-content: center;
        border-radius: 50%;
        background: linear-gradient(145deg, #1B1327, #2A163E);
        border: 1px solid var(--nr-gold);
        color: var(--nr-gold-soft);
        font-size: 15px;
        box-shadow: 0 8px 16px rgba(0,0,0,0.35);
    }

    .nr-helper-line {
        margin-top: 9px;
        color: var(--nr-muted);
        font-size: 12.5px;
        line-height: 1.5;
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
    "incident_memory": None,
    "recurrence_analysis": None,
    "replay_result": None,
    "verification_result": None,
    "proof_result": None,
}


for key, default_value in DEFAULT_STATE.items():
    if key not in st.session_state:
        st.session_state[key] = default_value


BOB_IMAGE_BASE64 = "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"

# ---------------------------------------------------------------------
# Bob mascot — floating companion that reacts to workflow state
# ---------------------------------------------------------------------

BOB_ICON_WELCOME = """
<svg class="nr-bob-icon-welcome" viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
    <defs>
        <linearGradient id="bobHeadWelcome" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stop-color="#CBA6FF"/>
            <stop offset="100%" stop-color="#7C3AED"/>
        </linearGradient>
    </defs>
    <path d="M22 46 Q14 52 16 60" stroke="#5B2FA8" stroke-width="6" fill="none" stroke-linecap="round"/>
    <path d="M42 46 Q54 40 51 25" stroke="#5B2FA8" stroke-width="6" fill="none" stroke-linecap="round"/>
    <circle cx="51" cy="22" r="5.2" fill="#CBA6FF"/>
    <path d="M56 16 L59 12 M59 18 L63 16 M55 22 L59 24" stroke="#F1C21B" stroke-width="2" stroke-linecap="round"/>
    <rect x="10" y="40" width="44" height="20" rx="10" fill="#160C24" stroke="#3C2C57" stroke-width="1.5"/>
    <circle cx="32" cy="50" r="4" fill="#A855F7"/>
    <line x1="32" y1="9" x2="32" y2="2" stroke="#F1C21B" stroke-width="2" stroke-linecap="round"/>
    <circle cx="32" cy="2" r="2.4" fill="#F1C21B"/>
    <rect x="14" y="9" width="36" height="30" rx="12" fill="url(#bobHeadWelcome)" stroke="#3C2C57" stroke-width="1.5"/>
    <circle cx="25" cy="24" r="3.6" fill="#0C0812"/>
    <circle cx="39" cy="24" r="3.6" fill="#0C0812"/>
    <circle cx="26.3" cy="22.8" r="1" fill="#fff"/>
    <circle cx="40.3" cy="22.8" r="1" fill="#fff"/>
    <path d="M26 31 Q32 35.5 38 31" stroke="#0C0812" stroke-width="2" fill="none" stroke-linecap="round"/>
</svg>
"""

BOB_ICON_INVESTIGATING = """
<svg class="nr-bob-icon-investigating" viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
    <defs>
        <linearGradient id="bobHeadInvestigating" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stop-color="#CBA6FF"/>
            <stop offset="100%" stop-color="#7C3AED"/>
        </linearGradient>
    </defs>
    <path d="M22 46 Q16 51 18 59" stroke="#5B2FA8" stroke-width="6" fill="none" stroke-linecap="round"/>
    <path d="M44 46 Q53 38 47 27" stroke="#5B2FA8" stroke-width="6" fill="none" stroke-linecap="round"/>
    <rect x="10" y="40" width="44" height="20" rx="10" fill="#160C24" stroke="#3C2C57" stroke-width="1.5"/>
    <circle cx="32" cy="50" r="4" fill="#F1C21B"/>
    <line x1="32" y1="9" x2="32" y2="2" stroke="#F1C21B" stroke-width="2" stroke-linecap="round"/>
    <circle cx="32" cy="2" r="2.4" fill="#F1C21B"/>
    <rect x="14" y="9" width="36" height="30" rx="12" fill="url(#bobHeadInvestigating)" stroke="#3C2C57" stroke-width="1.5"/>
    <circle cx="25" cy="24" r="3.6" fill="#0C0812"/>
    <path d="M26 31 Q32 33 38 31" stroke="#0C0812" stroke-width="2" fill="none" stroke-linecap="round"/>
    <circle cx="41" cy="23" r="10" fill="rgba(241,194,27,0.12)" stroke="#F1C21B" stroke-width="3"/>
    <circle cx="41" cy="23" r="3.6" fill="#0C0812"/>
    <line x1="48" y1="30" x2="55" y2="37" stroke="#F1C21B" stroke-width="3.5" stroke-linecap="round"/>
</svg>
"""

BOB_ICON_THINKING = """
<svg class="nr-bob-icon-thinking" viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
    <defs>
        <linearGradient id="bobHeadThinking" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stop-color="#CBA6FF"/>
            <stop offset="100%" stop-color="#7C3AED"/>
        </linearGradient>
    </defs>
    <path d="M42 46 Q52 50 50 59" stroke="#5B2FA8" stroke-width="6" fill="none" stroke-linecap="round"/>
    <path d="M22 46 Q17 36 27 31" stroke="#5B2FA8" stroke-width="6" fill="none" stroke-linecap="round"/>
    <circle cx="27" cy="29" r="5" fill="#CBA6FF"/>
    <rect x="10" y="40" width="44" height="20" rx="10" fill="#160C24" stroke="#3C2C57" stroke-width="1.5"/>
    <circle cx="32" cy="50" r="4" fill="#F1C21B">
        <animate attributeName="opacity" values="1;0.35;1" dur="1.4s" repeatCount="indefinite"/>
    </circle>
    <line x1="32" y1="9" x2="32" y2="2" stroke="#F1C21B" stroke-width="2" stroke-linecap="round"/>
    <circle cx="32" cy="2" r="2.4" fill="#F1C21B"/>
    <rect x="14" y="9" width="36" height="28" rx="12" fill="url(#bobHeadThinking)" stroke="#3C2C57" stroke-width="1.5"/>
    <line x1="21" y1="19" x2="27" y2="21" stroke="#0C0812" stroke-width="2" stroke-linecap="round"/>
    <line x1="43" y1="19" x2="37" y2="21" stroke="#0C0812" stroke-width="2" stroke-linecap="round"/>
    <circle cx="25" cy="25" r="3.2" fill="#0C0812"/>
    <circle cx="39" cy="25" r="3.2" fill="#0C0812"/>
    <circle cx="32" cy="32" r="1.6" fill="#0C0812"/>
    <circle cx="47" cy="8" r="2.2" fill="#F1C21B" opacity="0.85">
        <animate attributeName="opacity" values="0.3;1;0.3" dur="1.4s" repeatCount="indefinite"/>
    </circle>
    <circle cx="53" cy="14" r="1.6" fill="#F1C21B" opacity="0.6">
        <animate attributeName="opacity" values="1;0.3;1" dur="1.4s" begin="0.3s" repeatCount="indefinite"/>
    </circle>
    <circle cx="55" cy="21" r="1.2" fill="#F1C21B" opacity="0.4">
        <animate attributeName="opacity" values="0.3;1;0.3" dur="1.4s" begin="0.6s" repeatCount="indefinite"/>
    </circle>
</svg>
"""

BOB_ICON_VERDICT = """
<svg class="nr-bob-icon-verdict" viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
    <defs>
        <linearGradient id="bobHeadVerdict" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stop-color="#CBA6FF"/>
            <stop offset="100%" stop-color="#7C3AED"/>
        </linearGradient>
    </defs>
    <path d="M20 47 Q17 52 22 56" stroke="#5B2FA8" stroke-width="6" fill="none" stroke-linecap="round"/>
    <path d="M44 47 Q47 52 42 56" stroke="#5B2FA8" stroke-width="6" fill="none" stroke-linecap="round"/>
    <rect x="10" y="41" width="44" height="19" rx="10" fill="#160C24" stroke="#3C2C57" stroke-width="1.5"/>
    <path d="M17 51 L32 47 L47 51 L47 58 L32 54 L17 58 Z" fill="#F5F1FB" stroke="#3C2C57" stroke-width="1.2"/>
    <line x1="32" y1="47" x2="32" y2="54" stroke="#3C2C57" stroke-width="1"/>
    <line x1="20" y1="51.5" x2="29" y2="49.5" stroke="#B8ACC9" stroke-width="1"/>
    <line x1="20" y1="54.5" x2="29" y2="52.5" stroke="#B8ACC9" stroke-width="1"/>
    <line x1="35" y1="49.5" x2="44" y2="51.5" stroke="#B8ACC9" stroke-width="1"/>
    <line x1="35" y1="52.5" x2="44" y2="54.5" stroke="#B8ACC9" stroke-width="1"/>
    <line x1="32" y1="9" x2="32" y2="2" stroke="#F1C21B" stroke-width="2" stroke-linecap="round"/>
    <circle cx="32" cy="2" r="2.4" fill="#F1C21B"/>
    <rect x="14" y="9" width="36" height="30" rx="12" fill="url(#bobHeadVerdict)" stroke="#3C2C57" stroke-width="1.5"/>
    <circle cx="25" cy="24" r="3.6" fill="#0C0812"/>
    <circle cx="39" cy="24" r="3.6" fill="#0C0812"/>
    <circle cx="26.3" cy="22.8" r="1" fill="#fff"/>
    <circle cx="40.3" cy="22.8" r="1" fill="#fff"/>
    <path d="M26 31 Q32 35.5 38 31" stroke="#0C0812" stroke-width="2" fill="none" stroke-linecap="round"/>
    <circle cx="46" cy="14" r="7" fill="#0C0812" stroke="#F1C21B" stroke-width="1.6"/>
    <path d="M43 14 L45.3 16.4 L49.5 11.6" stroke="#F1C21B" stroke-width="1.8" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
"""


def render_bob_mascot() -> None:
    """
    Render Bob as a floating companion whose pose and message react
    to where the person currently is in the NoRepeat workflow.
    Purely presentational: reads existing session state, changes
    nothing about it.
    """
    if st.session_state.proof_result:
        state = "verdict"
        tag = "VERDICT"
        message = (
            "Case closed. I reproduced the incident, verified the fix, "
            "and sealed the Proof of Non-Recurrence below."
        )
    elif st.session_state.baseline_result:
        state = "thinking"
        tag = "ANALYZING"
        message = (
            "Give me a moment — I'm correlating the incident, the code "
            "and the tests before I report back."
        )
    elif st.session_state.session_id:
        state = "investigating"
        tag = "INVESTIGATING"
        message = (
            "Got it. Let me take a closer look at this codebase before "
            "we go any further."
        )
    else:
        state = "welcome"
        tag = "BOB · AUDITOR"
        message = (
            "Hi, I'm Bob. Load a repository and an incident report and "
            "I'll audit it with you, step by step."
        )

    dots = '<span class="nr-bob-dots"><span></span><span></span><span></span></span>' if state == "thinking" else ""

    st.markdown(
        f"""
        <div class="nr-bob-wrap nr-bob-{state}">
            <div class="nr-bob-bubble">
                <span class="nr-bob-tag">{tag}{dots}</span>
                {message}
            </div>
            <div class="nr-bob-avatar">
                {BOB_ICON_WELCOME}
                {BOB_ICON_INVESTIGATING}
                {BOB_ICON_THINKING}
                {BOB_ICON_VERDICT}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# Floating mascot disabled in favor of the sidebar Bob assistant panel.




# ---------------------------------------------------------------------
# Sidebar Bob assistant
# ---------------------------------------------------------------------

def resolve_bob_assistant_state(
    repository_source: str | None = None,
    repository_url: str = "",
    uploaded_zip_name: str | None = None,
) -> dict[str, str]:
    """Return Bob's visual state without pretending Bob has run yet."""
    status = st.session_state.session_status or {}

    if st.session_state.proof_result:
        return {
            "state": "verdict",
            "tag": "BOB · VERDICT",
            "title": "Audit complete",
            "emoji": "📘",
            "message": (
                "The historical recurrence was reproduced, remediated and "
                "verified. The final evidence is ready below."
            ),
            "helper": "Proof of Non-Recurrence is ready for review.",
        }

    if status.get("recurrence_analysis_completed") or st.session_state.baseline_result:
        return {
            "state": "thinking",
            "tag": "BOB · ANALYSIS",
            "title": "Historical recurrence workflow",
            "emoji": "🧠",
            "message": (
                "The candidate revision and historical postmortem are ready. "
                "Bob will learn the incident pattern and compare it with the code."
            ),
            "helper": "Bob integration is the next implementation phase.",
        }

    if st.session_state.session_id:
        incident = status.get("incident")
        return {
            "state": "investigating",
            "tag": "BOB · INVESTIGATING",
            "title": "Candidate prepared",
            "emoji": "🔎",
            "message": (
                "The code snapshot is loaded. "
                + (
                    "Your postmortem is attached and ready for me to learn."
                    if incident
                    else "Attach the historical postmortem so I can learn what must not repeat."
                )
            ),
            "helper": "The postmortem always comes from the user, not the repository.",
        }

    if repository_url.strip() or uploaded_zip_name or repository_source in {
        "GitHub repository",
        "ZIP upload",
    }:
        return {
            "state": "investigating",
            "tag": "BOB · INVESTIGATING",
            "title": "Source selected",
            "emoji": "🔎",
            "message": (
                "Good. Load the candidate code and I will prepare it for a "
                "historical recurrence audit."
            ),
            "helper": "GitHub can audit a branch, tag or commit. ZIP is a snapshot.",
        }

    return {
        "state": "welcome",
        "tag": "BOB · WELCOME",
        "title": "Welcome to NoRepeat",
        "emoji": "👋",
        "message": (
            "Hi, I'm Bob. Give me a code revision and a historical postmortem. "
            "I'll help determine whether your team is repeating a failure it already learned from."
        ),
        "helper": "Start with a GitHub repository or upload a ZIP snapshot.",
    }


def render_bob_assistant_panel(container, state_data: dict[str, str]) -> None:
    container.markdown(
        dedent(
            f"""
            <div class="nr-bob-panel nr-bob-panel-{state_data['state']}">
                <div class="nr-bob-panel-tag">{state_data['tag']}</div>
                <div class="nr-bob-panel-layout">
                    <div class="nr-bob-avatar-shell">
                        <img src="data:image/png;base64,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" alt="Bob assistant" />
                        <div class="nr-bob-mode-emoji">{state_data['emoji']}</div>
                    </div>
                    <div>
                        <div class="nr-bob-panel-title">{state_data['title']}</div>
                        <div class="nr-bob-panel-message">{state_data['message']}</div>
                    </div>
                </div>
                <div class="nr-helper-line">{state_data['helper']}</div>
            </div>
            """
        ),
        unsafe_allow_html=True,
    )

def clear_repository_source() -> None:
    """Return the repository selector to its initial unselected state."""
    st.session_state["repository_source_choice"] = None
    st.session_state.pop("project_zip", None)


# ---------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------

def api_request(
    method: str,
    endpoint: str,
    *,
    request_timeout: int = REQUEST_TIMEOUT,
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
            timeout=request_timeout,
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


def _clear_session_query_param() -> None:
    """Remove the resumable session identifier from the browser URL."""
    if "session" in st.query_params:
        del st.query_params["session"]


def sync_local_state_from_status(status: dict | None) -> None:
    """Keep Streamlit-local result state aligned with the backend manifest."""
    status = status or {}
    st.session_state.repository_loaded = bool(status.get("repository"))
    st.session_state.incident_loaded = bool(status.get("incident"))
    st.session_state.baseline_result = status.get("baseline")
    st.session_state.incident_memory = status.get("incident_memory")
    st.session_state.recurrence_analysis = status.get("recurrence_analysis")
    st.session_state.replay_result = status.get("replay")
    st.session_state.verification_result = status.get("verification")

    proof = status.get("proof") or {}
    if proof.get("status") == "VERIFIED":
        st.session_state.proof_result = proof
    elif proof.get("status") in {"PENDING", "READY", "FAILED"}:
        st.session_state.proof_result = None


def activate_session(manifest: dict) -> None:
    """Activate a backend session and make it survive browser refreshes."""
    session_id = manifest.get("session_id")
    if not session_id:
        return

    st.session_state.session_id = session_id
    st.session_state.session_status = manifest
    sync_local_state_from_status(manifest)
    st.query_params["session"] = session_id


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
        status = payload["data"]
        st.session_state.session_status = status
        sync_local_state_from_status(status)
        st.query_params["session"] = session_id

    return payload


def reset_local_state(*, clear_query: bool = True) -> None:
    """Reset local Streamlit state and optionally clear the resumable URL."""
    for key, default_value in DEFAULT_STATE.items():
        st.session_state[key] = default_value

    if clear_query:
        _clear_session_query_param()


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
    """Display workflow progress without marking failed operations as complete."""
    status = st.session_state.session_status or {}
    current_status = status.get("status", "NOT_STARTED")

    baseline = status.get("baseline")
    recurrence = status.get("recurrence_analysis")
    replay = status.get("replay")
    verification = status.get("verification")
    proof = status.get("proof") or {}

    guard = status.get("regression_guard")

    steps = [
        ("Candidate", "done" if status.get("repository") else "pending"),
        ("Postmortem", "done" if status.get("incident") else "pending"),
        (
            "Baseline",
            "done" if baseline and baseline.get("success")
            else "failed" if baseline is not None
            else "pending",
        ),
        ("Memory", "done" if status.get("incident_memory_ready") else "pending"),
        (
            "Recurrence",
            "detected" if recurrence and recurrence.get("detected")
            else "done" if recurrence is not None
            else "pending",
        ),
        ("Guard", "done" if guard else "pending"),
        (
            "Replay",
            "detected" if replay and replay.get("incident_reproduced")
            else "failed" if replay is not None
            else "pending",
        ),
        (
            "Verify",
            "done" if verification and verification.get("verified")
            else "failed" if verification is not None
            else "pending",
        ),
        ("Proof", "done" if proof.get("status") == "VERIFIED" else "pending"),
    ]

    st.subheader("Historical recurrence workflow")
    columns = st.columns(3) + st.columns(3) + st.columns(3)

    for column, (name, state) in zip(columns, steps):
        if state == "done":
            column.success(f"✓ {name}")
        elif state == "detected":
            column.warning(f"! {name}")
        elif state == "failed":
            column.error(f"✕ {name}")
        else:
            column.info(f"○ {name}")

    st.caption(f"Current session state: {current_status}")


def show_repository_summary(status: dict | None) -> None:
    if not status:
        return

    repository = status.get("repository") or {}
    if not repository:
        return

    source_type = repository.get("source_type", "unknown")
    revision = repository.get("requested_revision") or repository.get("resolved_revision")
    commit_sha = repository.get("commit_sha")

    cols = st.columns(3)
    cols[0].metric("Source", source_type.upper())
    cols[1].metric("Revision", revision or "default")
    cols[2].metric("Commit", commit_sha[:10] if commit_sha else "snapshot")


# ---------------------------------------------------------------------
# Resume session after browser refresh
# ---------------------------------------------------------------------

if not st.session_state.session_id:
    query_session = st.query_params.get("session")
    if isinstance(query_session, list):
        query_session = query_session[0] if query_session else None

    if isinstance(query_session, str) and query_session.strip():
        payload = api_request(
            "GET",
            f"/api/sessions/{query_session.strip()}",
        )
        if payload:
            activate_session(payload["data"])
        else:
            _clear_session_query_param()


# ---------------------------------------------------------------------
# Header / Mini landing page
# ---------------------------------------------------------------------

st.markdown(
    dedent(
        f"""
        <div class="nr-hero">
            <div class="nr-stamp"><img src="data:image/png;base64,{BOB_IMAGE_BASE64}" alt="Bob auditor"></div>
            <div class="nr-badge">
                <span class="nr-live-dot"></span>
                HISTORICAL RECURRENCE AUDITOR
            </div>
            <div class="nr-title">No<span>Repeat</span></div>
            <div class="nr-tagline">
                <strong>Turn past incidents into executable memory.</strong>
                Audit new code against failures your team has already learned from.
            </div>
            <div class="nr-techline">
                POSTMORTEM → INCIDENT MEMORY → CANDIDATE REVISION → RECURRENCE → REPLAY → VERIFY
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
            <div class="nr-card-number">01 / LEARN</div>
            <div class="nr-card-title">User-supplied postmortem</div>
            <div class="nr-card-description">
                The incident report comes from the user. Bob will later extract the
                root cause, violated security property and reusable historical pattern.
            </div>
        </div>
        <div class="nr-card">
            <div class="nr-card-number">02 / REMEMBER</div>
            <div class="nr-card-title">Persistent incident memory</div>
            <div class="nr-card-description">
                NoRepeat stores Bob's structured understanding so the lesson survives
                beyond one chat and can be reused against future code revisions.
            </div>
        </div>
        <div class="nr-card">
            <div class="nr-card-number">03 / PREVENT</div>
            <div class="nr-card-title">Detect historical recurrence</div>
            <div class="nr-card-description">
                A new branch or commit is compared with incident memory. If the same
                root-cause pattern returns, NoRepeat proves it through replay and tests.
            </div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------
# Sidebar / system status
# ---------------------------------------------------------------------

with st.sidebar:
    st.header("System")
    bob_sidebar_placeholder = st.empty()

    backend_healthy = check_backend_health()
    if backend_healthy:
        st.success("Backend connected")
    else:
        st.error("Backend unavailable")

    st.caption(API_BASE_URL)

    if st.session_state.session_id:
        st.divider()
        st.caption("Current session")
        st.code(st.session_state.session_id, language="text")

        if st.button("Refresh session", use_container_width=True):
            refresh_session_status()
            st.rerun()

        if st.button("Delete session", use_container_width=True):
            payload = api_request(
                "DELETE",
                f"/api/sessions/{st.session_state.session_id}",
            )
            if payload:
                reset_local_state()
                st.rerun()

    st.divider()
    with st.expander("Maintenance / clean runtime data"):
        st.caption(
            "Deletes generated sessions, cloned repositories, runtime evidence and "
            "caches. Preserves .bob/, AGENTS.md, bob_sessions/, data/guards/ and "
            "data/incidents/. Learned incident memories are archived to data/guards/."
        )
        cleanup_confirmed = st.checkbox(
            "I understand this will remove all active runtime sessions.",
            key="cleanup_runtime_confirmed",
        )
        if st.button(
            "Clean generated runtime data",
            disabled=not cleanup_confirmed,
            use_container_width=True,
        ):
            headers = {}
            if CLEANUP_TOKEN:
                headers["X-NoRepeat-Cleanup-Token"] = CLEANUP_TOKEN

            payload = api_request(
                "POST",
                "/api/runtime/cleanup",
                headers=headers,
            )
            if payload:
                report = payload.get("data") or {}
                reset_local_state()
                st.success(
                    "Runtime data cleaned. "
                    f"Sessions removed: {report.get('workspaces_removed', 0)}. "
                    f"Incident memories archived: "
                    f"{len(report.get('archived_incident_memories', []))}."
                )
                st.rerun()

# ---------------------------------------------------------------------
# Step 1 - Candidate code
# ---------------------------------------------------------------------

st.markdown(
    """
    <div class="nr-section-label">STEP 01 · CANDIDATE CODE</div>
    <div class="nr-section-title">Select the code you want to audit</div>
    <div class="nr-section-description">
        GitHub sessions can target a branch, tag or commit. ZIP uploads are treated
        as a fixed candidate snapshot.
    </div>
    """,
    unsafe_allow_html=True,
)

source_col, clear_col = st.columns([0.92, 0.08], vertical_alignment="bottom")

with source_col:
    repository_source = st.radio(
        "Project source",
        ["GitHub repository", "ZIP upload"],
        index=None,
        horizontal=True,
        key="repository_source_choice",
    )

with clear_col:
    if repository_source is not None:
        st.button(
            "✕",
            key="clear_repository_source",
            help="Clear project source",
            use_container_width=True,
            on_click=clear_repository_source,
        )

repository_url = ""
revision_to_audit = ""
uploaded_zip = None

if repository_source is None:
    st.caption("Choose GitHub repository or ZIP upload to begin.")

elif repository_source == "GitHub repository":
    repository_url = st.text_input(
        "Public GitHub repository URL",
        placeholder="https://github.com/your-team/norepeat-demo-app",
    )
    revision_to_audit = st.text_input(
        "Revision to audit (optional)",
        placeholder="main, feature/admin-export, v1.2.0, or commit SHA",
        help=(
            "Leave blank to audit the repository's default checked-out revision. "
            "For the demo, use the branch or commit that represents the new change."
        ),
    )

    if st.button("Load candidate revision", type="primary"):
        if not repository_url.strip():
            st.warning("Enter a GitHub repository URL.")
        else:
            with st.spinner("Cloning repository and preparing candidate revision..."):
                payload = api_request(
                    "POST",
                    "/api/sessions/github",
                    json={
                        "repository_url": repository_url.strip(),
                        "revision": revision_to_audit.strip() or None,
                    },
                )

            if payload:
                manifest = payload["data"]
                activate_session(manifest)
                st.rerun()

elif repository_source == "ZIP upload":
    uploaded_zip = st.file_uploader(
        "Upload candidate ZIP snapshot",
        type=["zip"],
        key="project_zip",
    )
    st.caption("ZIP mode audits exactly the uploaded snapshot; it has no Git revision selector.")

    if st.button("Load ZIP snapshot", type="primary"):
        if uploaded_zip is None:
            st.warning("Select a ZIP project first.")
        else:
            with st.spinner("Preparing project workspace..."):
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
                activate_session(manifest)
                st.rerun()

uploaded_zip_name = uploaded_zip.name if uploaded_zip is not None else None
render_bob_assistant_panel(
    bob_sidebar_placeholder,
    resolve_bob_assistant_state(
        repository_source=repository_source,
        repository_url=repository_url,
        uploaded_zip_name=uploaded_zip_name,
    ),
)

if not st.session_state.session_id:
    st.info("Load candidate code to begin a NoRepeat session.")
    st.stop()

refresh_session_status()
current_status = st.session_state.session_status or {}
show_repository_summary(current_status)

# Allow switching candidate revision without losing learned incident memory.
repository_meta = current_status.get("repository") or {}
if repository_meta.get("supports_revision_switching"):
    with st.expander("Change candidate revision"):
        new_revision = st.text_input(
            "Branch, tag or commit",
            key="change_candidate_revision",
            placeholder="feature/new-change",
        )
        if st.button("Switch candidate revision"):
            if not new_revision.strip():
                st.warning("Enter a revision first.")
            else:
                payload = api_request(
                    "PATCH",
                    f"/api/sessions/{st.session_state.session_id}/revision",
                    json={"revision": new_revision.strip()},
                )
                if payload:
                    st.session_state.session_status = payload["data"]
                    st.session_state.baseline_result = None
                    st.session_state.recurrence_analysis = None
                    st.session_state.replay_result = None
                    st.session_state.verification_result = None
                    st.session_state.proof_result = None
                    st.rerun()

st.divider()

# ---------------------------------------------------------------------
# Step 2 - User-supplied postmortem
# ---------------------------------------------------------------------

st.markdown(
    """
    <div class="nr-section-label">STEP 02 · HISTORICAL INCIDENT</div>
    <div class="nr-section-title">Upload the historical postmortem</div>
    <div class="nr-section-description">
        This document is supplied by the user. NoRepeat does not expect the incident
        report to exist inside the repository and does not invent the historical event.
    </div>
    """,
    unsafe_allow_html=True,
)

if not current_status.get("incident"):
    incident_file = st.file_uploader(
        "Historical postmortem",
        type=["md", "txt"],
        key="incident_report",
    )

    if st.button("Attach postmortem"):
        if incident_file is None:
            st.warning("Select a postmortem first.")
        else:
            with st.spinner("Attaching historical postmortem..."):
                payload = api_request(
                    "POST",
                    f"/api/sessions/{st.session_state.session_id}/incident",
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
                st.rerun()
else:
    incident = current_status["incident"]
    st.success(f"Postmortem attached: {incident.get('filename')}")
    st.caption(f"SHA-256: {incident.get('sha256')}")

if not current_status.get("incident"):
    st.info("Attach the historical postmortem before continuing.")
    st.stop()

st.divider()

# ---------------------------------------------------------------------
# Step 3 - Baseline
# ---------------------------------------------------------------------

st.markdown(
    """
    <div class="nr-section-label">STEP 03 · BASELINE</div>
    <div class="nr-section-title">Establish the candidate baseline</div>
    <div class="nr-section-description">
        Run the existing test suite before Bob changes anything. A passing baseline
        shows that ordinary coverage can miss the historical recurrence.
    </div>
    """,
    unsafe_allow_html=True,
)

if st.button("Run baseline tests", type="primary"):
    with st.spinner("Running the existing pytest suite..."):
        payload = api_request(
            "POST",
            f"/api/sessions/{st.session_state.session_id}/baseline",
        )
    if payload:
        st.session_state.baseline_result = payload["data"]
        refresh_session_status()

show_pytest_result("Baseline result", st.session_state.baseline_result)

refresh_session_status()
current_status = st.session_state.session_status or {}
display_workflow_status()
st.divider()

# ---------------------------------------------------------------------
# Step 4 - Incident memory (Bob integration point)
# ---------------------------------------------------------------------

st.markdown(
    """
    <div class="nr-section-label">STEP 04 · INCIDENT MEMORY</div>
    <div class="nr-section-title">Bob learns the postmortem</div>
    <div class="nr-section-description">
        Bob will extract the root cause, violated security property and historical
        pattern from the uploaded postmortem. NoRepeat persists that structured result
        so the lesson can be reused against future revisions.
    </div>
    """,
    unsafe_allow_html=True,
)

if current_status.get("incident_memory_ready"):
    st.success("Historical incident memory is ready.")
    memory = current_status.get("incident_memory", {}).get("memory", {})
    if memory:
        st.json(memory)
else:
    baseline = current_status.get("baseline") or {}
    learn_enabled = bool(baseline.get("success"))

    if st.button(
        "Learn incident with IBM Bob",
        type="primary",
        disabled=not learn_enabled,
    ):
        with st.spinner(
            "IBM Bob is learning the historical postmortem. This can take a few minutes..."
        ):
            payload = api_request(
                "POST",
                f"/api/sessions/{st.session_state.session_id}/bob/learn",
                request_timeout=BOB_REQUEST_TIMEOUT,
            )
        if payload:
            st.success("IBM Bob learned and persisted the historical incident memory.")
            refresh_session_status()
            st.rerun()

    if not learn_enabled:
        st.info("A passing baseline is required before Bob can learn the incident.")
    else:
        st.caption(
            "Bob will read only the uploaded postmortem during this phase and will "
            "persist structured Incident Memory automatically."
        )

# ---------------------------------------------------------------------
# Step 5 - Historical recurrence analysis
# ---------------------------------------------------------------------

st.markdown(
    """
    <div class="nr-section-label">STEP 05 · HISTORICAL RECURRENCE</div>
    <div class="nr-section-title">Compare the candidate with incident memory</div>
    <div class="nr-section-description">
        Bob will compare meaning, not keywords: the current implementation may look
        different while still recreating the same historical root cause.
    </div>
    """,
    unsafe_allow_html=True,
)

recurrence = current_status.get("recurrence_analysis")
if recurrence:
    recurrence_detected = recurrence.get("detected")
    if recurrence_detected is None:
        recurrence_detected = recurrence.get("recurrence_detected")

    if recurrence_detected:
        st.error("Historical recurrence detected.")
    else:
        st.success("No known historical recurrence detected for this candidate.")
    st.json(recurrence)
else:
    analyze_enabled = bool(
        current_status.get("incident_memory_ready")
        and (current_status.get("baseline") or {}).get("success")
    )

    if st.button(
        "Analyze recurrence with IBM Bob",
        type="primary",
        disabled=not analyze_enabled,
    ):
        with st.spinner(
            "IBM Bob is comparing the candidate revision with Incident Memory..."
        ):
            payload = api_request(
                "POST",
                f"/api/sessions/{st.session_state.session_id}/bob/analyze",
                request_timeout=BOB_REQUEST_TIMEOUT,
            )
        if payload:
            result = payload.get("data", {})
            analysis = result.get("analysis", {})
            if analysis.get("detected"):
                st.error("IBM Bob detected a historical recurrence.")
            else:
                st.success("IBM Bob found no known historical recurrence.")
            refresh_session_status()
            st.rerun()

    if not analyze_enabled:
        st.info(
            "A passing baseline and persisted Incident Memory are required before "
            "Bob can analyze recurrence."
        )
    else:
        st.caption(
            "Bob may use read-only parallel subagents to correlate the historical "
            "root cause, candidate behavior and existing test coverage."
        )

st.divider()

# ---------------------------------------------------------------------
# Step 6 - Regression guard generation
# ---------------------------------------------------------------------

st.markdown(
    """
    <div class="nr-section-label">STEP 06 · REGRESSION GUARD</div>
    <div class="nr-section-title">Turn the recurrence into a permanent test</div>
    <div class="nr-section-description">
        Bob converts the detected historical recurrence into one deterministic pytest
        regression guard. Bob is not allowed to modify production code or remediate
        the issue during this phase.
    </div>
    """,
    unsafe_allow_html=True,
)

recurrence_detected = bool(
    recurrence
    and (
        recurrence.get("detected") is True
        or recurrence.get("recurrence_detected") is True
    )
)

guard = current_status.get("regression_guard") or {}

if guard:
    st.success("IBM Bob regression guard is ready.")
    st.code(guard.get("test_path", "Generated test path unavailable"), language="text")
    if guard.get("security_property"):
        st.caption(f"Security property: {guard.get('security_property')}")
else:
    if st.button(
        "Generate regression guard with IBM Bob",
        type="primary",
        disabled=not recurrence_detected,
    ):
        with st.spinner(
            "IBM Bob is generating the historical regression guard..."
        ):
            payload = api_request(
                "POST",
                f"/api/sessions/{st.session_state.session_id}/bob/generate-guard",
                request_timeout=BOB_REQUEST_TIMEOUT,
            )
        if payload:
            result = payload.get("data", {})
            generated_guard = result.get("guard", {})
            st.success(
                "IBM Bob generated the regression guard: "
                + str(generated_guard.get("test_path", "test created"))
            )
            refresh_session_status()
            st.rerun()

    if not recurrence_detected:
        st.caption(
            "Guard generation unlocks only after IBM Bob detects a historical recurrence."
        )

st.divider()

# ---------------------------------------------------------------------
# Step 7 - Incident replay
# ---------------------------------------------------------------------

st.markdown(
    """
    <div class="nr-section-label">STEP 07 · INCIDENT REPLAY</div>
    <div class="nr-section-title">Prove the recurrence</div>
    <div class="nr-section-description">
        NoRepeat independently runs Bob's generated regression guard. A failing replay
        before remediation is evidence that the historical condition can be reproduced.
    </div>
    """,
    unsafe_allow_html=True,
)

incident_test_path = str(guard.get("test_path") or "")
if incident_test_path:
    st.text_input(
        "Generated regression test path",
        value=incident_test_path,
        disabled=True,
    )
else:
    st.info("Generate the regression guard before running incident replay.")

replay_enabled = bool(recurrence_detected and incident_test_path)
if st.button("Run incident replay", disabled=not replay_enabled):
    with st.spinner("Replaying historical recurrence..."):
        payload = api_request(
            "POST",
            f"/api/sessions/{st.session_state.session_id}/replay",
            json={"incident_test_path": incident_test_path},
        )
    if payload:
        st.session_state.replay_result = payload["data"]
        refresh_session_status()

if not replay_enabled:
    st.caption("Replay unlocks after IBM Bob generates the regression guard.")

if st.session_state.replay_result:
    show_pytest_result(
        "Historical recurrence replay",
        st.session_state.replay_result.get("pytest"),
    )

st.divider()

# ---------------------------------------------------------------------
# Step 8 - Bob remediation + verification
# ---------------------------------------------------------------------

st.markdown(
    """
    <div class="nr-section-label">STEP 08 · REMEDIATE & VERIFY</div>
    <div class="nr-section-title">Fix without erasing the evidence</div>
    <div class="nr-section-description">
        Bob should apply the smallest justified remediation, preserve the regression
        test, then NoRepeat requires both the incident test and full suite to pass.
    </div>
    """,
    unsafe_allow_html=True,
)

replay_data = st.session_state.replay_result or current_status.get("replay")
verify_enabled = bool(replay_data and replay_data.get("incident_reproduced"))

if st.button("Verify after Bob fix", disabled=not verify_enabled):
    with st.spinner("Verifying remediation..."):
        payload = api_request(
            "POST",
            f"/api/sessions/{st.session_state.session_id}/verify",
            json={"incident_test_path": incident_test_path},
        )
    if payload:
        st.session_state.verification_result = payload["data"]
        refresh_session_status()

if not verify_enabled:
    st.caption("Verification unlocks after recurrence has been reproduced.")

if st.session_state.verification_result:
    verification = st.session_state.verification_result
    show_pytest_result("Incident regression test", verification.get("incident_test"))
    show_pytest_result("Full project test suite", verification.get("full_test_suite"))

st.divider()

# ---------------------------------------------------------------------
# Step 9 - Proof
# ---------------------------------------------------------------------

st.markdown(
    """
    <div class="nr-section-label">STEP 09 · AUDIT EVIDENCE</div>
    <div class="nr-section-title">Proof of Non-Recurrence</div>
    <div class="nr-section-description">
        The final artifact links the user postmortem, persisted incident memory,
        candidate revision, recurrence evidence, replay and verification results.
    </div>
    """,
    unsafe_allow_html=True,
)

verification_data = (
    st.session_state.verification_result
    or current_status.get("verification")
)
proof_enabled = bool(verification_data and verification_data.get("verified"))

if st.button("Generate proof", type="primary", disabled=not proof_enabled):
    with st.spinner("Generating Proof of Non-Recurrence..."):
        payload = api_request(
            "POST",
            f"/api/sessions/{st.session_state.session_id}/proof",
        )
    if payload:
        st.session_state.proof_result = payload["data"]
        refresh_session_status()

if not proof_enabled:
    st.caption("Proof unlocks after remediation verification passes.")

if st.session_state.proof_result:
    st.success("🛡️ VERIFIED — Proof of Non-Recurrence generated.")
    st.json(st.session_state.proof_result)

st.divider()
st.caption(
    "NoRepeat proves non-recurrence only for the historical incident pattern "
    "represented by the persisted incident memory and generated regression test. "
    "It does not claim that the application is free of all vulnerabilities."
)
