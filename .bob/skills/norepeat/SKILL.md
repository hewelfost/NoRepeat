---
name: norepeat
description: >-
  Use when auditing candidate code against a historical postmortem to detect
  semantic recurrence of the same root cause and produce a regression test
  and minimal remediation.
---

# NoRepeat Skill

Follow these steps in strict order. Do not skip or reorder them.

## Step 1 — Learn: extract Incident Memory

Read the postmortem supplied by the user. Produce a short **Incident Memory**
block with exactly these fields:

```
Root Cause    : <one sentence>
Trigger       : <what condition activated the bug>
Blast Radius  : <what failed and how widely>
Fix Applied   : <what the original fix did>
Recurrence Signature : <the code pattern or invariant whose violation causes this bug>
```

Do not proceed until the Incident Memory is complete.

## Step 2 — Analyze: check candidate code for recurrence

Examine the candidate code provided by the user.

- Map the **Recurrence Signature** onto the candidate code.
- Look for semantic equivalence, not textual similarity.
- If no recurrence is found, state that clearly and stop.
- If a potential recurrence is found, cite the exact file, function, and
  line(s) and explain the causal link to the Recurrence Signature.

## Step 3 — Test first: write a regression test

Only if Step 2 confirmed a recurrence:

- Write a minimal `pytest` test that directly exercises the recurrence site
  and asserts the failure condition from the Incident Memory.
- Place the test in the project's test directory (or ask the user where).
- Do **not** write any remediation code yet.

## Step 4 — Replay gate: wait for RED confirmation

Ask the user to run:

```
pytest <test_file>::<test_name> -v
```

Do not continue until the user confirms the test **fails (RED)**.
If they report GREEN, re-examine the test — it may not be exercising the
recurrence correctly.

## Step 5 — Remediate minimally

Apply the smallest code change that makes the regression test pass GREEN.

Constraints:
- Touch only the recurrence site identified in Step 2.
- Do not refactor, rename, or restructure surrounding code.
- Do not add defensive patches to unrelated code.

## Step 6 — Verify GREEN

Ask the user to re-run the same pytest command and confirm it passes (GREEN).
If it still fails, revise the remediation — do not weaken or remove the test.

## Step 7 — Report

Produce a concise summary:

| Field | Value |
|---|---|
| Recurrence confirmed | yes / no |
| Regression test | `<path>::<name>` |
| Remediation | `<file>:<line-range>` — one-line description |
| Test status | RED -> GREEN confirmed |
