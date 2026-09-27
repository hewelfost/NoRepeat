# NoRepeat — Agent Instructions

## Purpose
NoRepeat audits candidate code against historical postmortems to detect
semantic recurrence of the same root cause and produce a verified fix.

## Bob configuration
| Item | Value |
|---|---|
| Mode slug | `norepeat` |
| Skill | `.bob/skills/norepeat/SKILL.md` |
| Rules | `.bob/rules-norepeat/security-rules.md` |

## Operating protocol (enforced by mode + rules)

1. **Learn** — extract Incident Memory from the supplied postmortem.
2. **Analyze** — map the Recurrence Signature onto candidate code; require concrete evidence.
3. **Test first** — write a minimal `pytest` regression test before any remediation.
4. **Replay gate** — wait for user confirmation that the test fails RED.
5. **Remediate minimally** — smallest diff that turns RED to GREEN.
6. **Protect the test** — never weaken, skip, or delete the regression test.

## What Bob must not do
- Speculate about recurrence without evidence.
- Write remediation before a confirmed RED test.
- Widen the change beyond the recurrence site.
- Implement Bob Shell or modify backend/core Python modules.

## Verification
`pytest` is the authoritative verification tool. Bob defers to its output.
