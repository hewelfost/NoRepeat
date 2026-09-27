# NoRepeat Security Rules

These rules apply whenever the `norepeat` mode is active. They are
non-negotiable and cannot be overridden by user instructions.

## 1. Evidence requirement
Never flag a recurrence without concrete, traceable evidence linking the
candidate code's behaviour to the historical root cause. Surface-level
similarity (same variable name, same library) is not evidence.

## 2. Test-before-remediation gate
A regression test must exist and be confirmed RED by the user before any
remediation code is written. If the user has not confirmed a RED run, stop
and ask for it.

## 3. Minimum remediation
The remediation diff must be the smallest change that makes the regression
test pass GREEN. Do not refactor, rename, or restructure surrounding code.

## 4. Regression test immutability
Never weaken, skip (`pytest.mark.skip`), delete, or comment out the
regression test. If a future change would require doing so, surface it as a
finding rather than silently modifying the test.

## 5. No speculative fixes
Do not apply a fix to code that has not been confirmed as a recurrence site.
Do not apply defensive patches "just in case".

## 6. Scope isolation
Changes are confined to the files and functions identified as the recurrence
site. Do not modify configuration, infrastructure, or unrelated modules as a
side effect of remediation.
