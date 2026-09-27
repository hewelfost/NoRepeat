🛡️ NoRepeat
Incident Replay & Proof of Non-Recurrence powered by IBM Bob 2.0
> *"Your team already paid for this bug once. Don’t pay for it twice."*
NoRepeat is a developer productivity and security tool built for the IBM Bob 2.0 Hackathon (48h). It converts historical engineering knowledge (postmortems, incident reports) into executable and verifiable tests directly within the development cycle.
⚠️ The Problem
When a production incident occurs, teams write a detailed postmortem. However:
The knowledge remains in human text (documents, tickets), far from the code.
Months later, another developer might reintroduce the exact same bug.
Preventive "action items" are often forgotten or not implemented as actual tests.
Recurrences force teams to repeat the diagnosis, mitigation, and fixing processes.
💡 The Solution
NoRepeat automates the post-incident learning workflow. IBM Bob 2.0 acts as the intelligent orchestrator that:
Reads a postmortem in Markdown.
Understands the Root Cause and maps it to the affected code.
Reproduces the incident by generating a minimal regression test (which must fail).
Applies the fix to the vulnerable code.
Re-executes the test to confirm success.
Generates a verifiable Proof of Non-Recurrence.
🛠️ Tech Stack
The architecture is designed as a monolithic MVP for local execution:
AI / Agent: IBM Bob IDE 2.0.2+ (Document Understanding, Agent Mode, Subagents).
Vulnerable Application (Fixture): Python 3.11+ with FastAPI.
Replay Engine (Testing): `pytest`.
Backend / Orchestrator: Flask.
Frontend / Dashboard: Streamlit.
Artifacts: Markdown (incidents), YAML (guardrails), JSON (evidence).
📂 Project Structure
```text
norepeat_mvp/
├── .bob/                            # Local IBM Bob configuration
├── AGENTS.md                        # Stable context and rules for Bob 
├── core/
│   ├── __init__.py
|   ├── bob_runner.py
|   ├── incident_manager.py
|   ├── orchestrator.py
|   ├── replay_engine.py             # pytest wrapper and evidence capture
│   └── repository_manager.py              # Workflow state
├── data/
│   ├── incidents/                   # Input folder (e.g., INC-042.md)
│   ├── guards/                      # Guardrails in YAML
│   └── evidence/                    # Proof of Non-Recurrence output in JSON
├── bob_sessions/                    # Bobcoin consumption screenshots (Hackathon requirement)
├── backend_api.py                   # Flask API for the dashboard
├── dashboard.py                     # Streamlit interface
└── requirements.txt
```
🚀 How to Run the Demo (For Judges)
This project is designed to be executed and orchestrated directly from IBM Bob IDE.
Step 1: Setup
Clone this repository and open it in IBM Bob IDE 2.0.2+.
Install the Python dependencies:
```bash
   pip install -r requirements.txt
   ```
Start the Dashboard in an integrated terminal to view the progress:
```bash
   streamlit run dashboard.py
   ```
Step 2: Execute the workflow with IBM Bob
Open the IBM Bob IDE chat and use the following operational prompt to trigger the Incident Replay:
> "Analyze `@data/incidents/INC-042.md`. Before modifying code:
> 1. Identify the root cause and the minimum reproduction condition.
> 2. Use separate subagents to review the incident, codebase, and tests.
> 3. Locate the related files (e.g., `@app.py`).
> 4. Create and execute a test using pytest that reproduces the incident (it must fail).
> 5. Only if the test fails as expected, apply the fix to the code.
> 6. Re-execute the complete test suite and save the before/after evidence in `@data/evidence/INC-042.json`.
> IMPORTANT: Do not modify the postmortem to make the test pass."
Step 3: Verification
Watch how Bob uses Agent Mode and launches parallel Subagents to investigate.
Review the automatically generated `test_INC_042.py` file.
Check the Streamlit dashboard to see the final incident status change to VERIFIED along with the Proof of Non-Recurrence.
🤖 IBM Bob 2.0 Integration (Hackathon Criteria)
NoRepeat meets the challenge requirements by deeply integrating Bob's core capabilities:
Document Understanding: Used to read and interpret the human incident report (`.md`).
Parallel Tasks & Subagents: Separates incident analysis, code review, and test review into distinct agents to avoid context pollution.
Agent Mode (Edit & Execute): Writes test code, runs `pytest` in the terminal, reads the results (Fail), edits `app.py` to apply the patch, and runs the tests again (Success).
Built in 48 hours for the IBM Bob 2.0 Hackathon hosted by lablab.ai