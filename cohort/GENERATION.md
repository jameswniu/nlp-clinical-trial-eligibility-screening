# How the tier-2 cohort was made

175 synthetic patients (`patient_T001` through `patient_T175`), generated in five
batches of 35 during the 2026-08-15 hardening pass. Every person is invented;
zero PHI by construction.

## Method

- Notes were authored by an LLM against a fixed schema: stated age must equal
  calendar age from the birth date at the pipeline's reference date
  (2024-05-01), every lab value mentioned in a note must exist as a lab row
  with a matching month, smoker status must match the note unless a planted
  mismatch documents the conflict.
- Each batch carries a fixed trap quota, recorded per patient in
  `traps.json`: 4 negation, 3 missing-lab, 3 borderline-age, 2
  smoker-mismatch, 2 explicit-numeric per batch (70 traps total), the other
  21 patients per batch clean.
- Assembly validation is mechanical (`ages recomputed from DOB, ASCII-only
  notes, id continuity, duplicate detection`); one batch was additionally
  checked by a second model, the rest by the assembly script plus spot
  reading.

## What the traps are for

The manifest is the verification instrument for this tier: instead of hand
reading 350 decisions, the audit checks that every planted trap landed where
it was aimed, plus a seeded random sample of clean decisions. The outcome is
recorded in the README ("Two tiers of golden data") and pinned in
`evals/known_wrong.expected.json`.

## The clean-decision sample

Drawn with `random.Random(7).sample` over the 210 clean (untrapped)
decisions and read by hand on 2026-08-15; in every case the eligibility
verdict follows the deterministic lane (age, smoker flag, most-recent lab)
and the evidence strings quote real note or data content:

- ONC-003-Prevention / patient_T138: False
- ONC-003-Prevention / patient_T067: False
- ONC-003-Prevention / patient_T169: True
- RESP-005-Cessation / patient_T104: False
- ONC-003-Prevention / patient_T023: False
- ONC-003-Prevention / patient_T033: False
- RESP-005-Cessation / patient_T061: False
- ONC-003-Prevention / patient_T053: False
- ONC-003-Prevention / patient_T156: False
- RESP-005-Cessation / patient_T074: False

## Regeneration

This cohort is committed and pinned; it is not regenerated. New patients
belong in a new batch range with their own manifest entries, re-audited
before pinning.
