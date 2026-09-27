# NoRepeat session-safety update

This revision addresses four workflow problems:

1. **Hard runtime cleanup**
   - `Clean all generated runtime data` is now one click.
   - Deletes all active workspaces, cloned candidates, session copies of uploaded postmortems, generated Incident Memory, recurrence evidence, guards, replay/remediation/verification/proof artifacts, runtime evidence and caches.
   - Preserves `.bob/`, `AGENTS.md`, `bob_sessions/`, source code and predefined `data/incidents/` assets.

2. **Resume sessions**
   - Backend exposes `GET /api/sessions`.
   - Sidebar lists saved sessions and lets the user resume one.
   - Existing `?session=<id>` URL recovery still works.
   - `Start another session` leaves the current backend session saved instead of deleting it.

3. **Safe branch/commit switching**
   - A new revision is resolved before the existing candidate is cleaned, so a typo cannot damage the current session.
   - On successful switch, Git reset/clean removes generated tests, remediation changes and caches from the old candidate.
   - NoRepeat also deletes candidate-specific recurrence/proof artifacts and runtime evidence while preserving the historical postmortem and Incident Memory.
   - The next revision starts again from Baseline, without stale candidate files.

4. **Readable UI**
   - Custom small text has a minimum size of 14 px.
   - Streamlit captions/widget labels/sidebar helper text are also forced to at least 14 px.

## Important production note

Session resume depends on the backend filesystem. On Railway, attach persistent storage/volume to the backend if sessions must survive service redeploys or container replacement. Browser refresh/exit works with the current code as long as the backend session files still exist.
