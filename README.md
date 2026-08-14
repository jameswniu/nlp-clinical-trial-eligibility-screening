<p align="center"><img src="assets/hero.svg" alt="Clinical trial eligibility screening that abstains instead of guessing: 50 golden decisions replayed in CI, 67 of 550 criterion verdicts abstain and say why, and hand-checking the shipped outputs caught 7 wrong admissions" width="100%"></p>

<div align="center">

<b><font size="6">Clinical Trial Eligibility Screening</font></b>

[![ci](https://github.com/jameswniu/nlp-clinical-trial-eligibility-screening/actions/workflows/ci.yml/badge.svg)](https://github.com/jameswniu/nlp-clinical-trial-eligibility-screening/actions/workflows/ci.yml)
![decisions](https://img.shields.io/badge/decisions-50_%C2%B7_25x2-dfe3e0?style=flat-square&labelColor=0c1013)
![agreement](https://img.shields.io/badge/agreement-50%2F50_recomputed-8f9491?style=flat-square&labelColor=0c1013)
![abstains](https://img.shields.io/badge/abstains-67_%C2%B7_each_says_why-8f9491?style=flat-square&labelColor=0c1013)
![tests](https://img.shields.io/badge/tests-41_passing-8f9491?style=flat-square&labelColor=0c1013)
![thresholds](https://img.shields.io/badge/thresholds-0%2F3_derived_%C2%B7_2_refuted-8f9491?style=flat-square&labelColor=0c1013)
![license](https://img.shields.io/badge/license-Apache--2.0-164e63?style=flat-square&labelColor=0c1013)

<strong>A screening pipeline that abstains instead of guessing, and the eval harness that caught it guessing anyway.</strong>

The interesting part is not the matching.<br/>
It is that hand-checking all 50 shipped decisions caught 7 wrong admissions the pipeline had reported with confidence,<br/>
and the gate that caught them now runs in CI, guarding even its own refuted thresholds.

<code>normalize -> compare -> abstain-or-decide -> explain</code>

</div>

---

## The 90 second tour

Every decision this pipeline makes carries its evidence: each criterion gets PASS, MAYBE, or FAIL with the exact comparison or match score that produced it, missing data abstains by name instead of defaulting, and one FAIL disqualifies no matter how good the rest looks. The eval layer is the larger half of the repo: a 50-decision golden dataset, hand-labelled exemplars for every semantic threshold, and a CI gate that replays all of it on every push.

| if you want | go to |
| --- | --- |
| the decision a reviewer would audit | [Why the MAYBE verdict is the point](#why-the-maybe-verdict-is-the-point) |
| the bug the gate caught | [Hand-checking 50 shipped decisions caught 7 wrong admissions](#hand-checking-50-shipped-decisions-caught-7-wrong-admissions) |
| the claim the labels killed | [The labels refuted my own thresholds](#the-labels-refuted-my-own-thresholds) |
| to run the whole gate free, in one command | [The gate CI actually runs](#the-gate-ci-actually-runs) |
| what is not claimed | [What this cannot tell you](#what-this-cannot-tell-you) |

## Why the MAYBE verdict is the point

Screening a patient against a trial protocol is a decision someone else has to defend later. So the unit of output here is not a score, it is a verdict with its receipt:

```
"HbA1c level must be less than 8.0%.":            "FAIL (HbA1c=8.1 not lt 8.0)"
"Patient must be between 50 and 70 years of age": "PASS (age=53 in range 50-70)"
"Spirometry FEV1 between 50-80% predicted.":      "MAYBE (no data for FEV1_percent)"
```

Three properties are load-bearing, and each is pinned by tests and the golden gate:

- **Missing data abstains by name.** No FEV1 in the record means `MAYBE (no data for FEV1_percent)`, never a silent pass. 67 of the 550 shipped criterion verdicts abstain, and every one names its gap.
- **One FAIL disqualifies.** Confidence is the mean of PASS=1 and MAYBE=0.5, and it is computed only when nothing failed. A patient with a disqualifying lab does not get argued back in by strong semantic matches elsewhere.
- **Confidence is arithmetic you can redo by hand.** The dry-run gate re-derives every stored confidence from its own stored verdicts, so the formula cannot drift without CI noticing.

Unstructured criteria (family history, occupational exposure, motivation to quit) are matched against the clinical note with MiniLM sentence embeddings, and the score ships inside the evidence string. That instrument is weak, which is the second finding below, and the reason the MAYBE tier and the FAIL override carry the safety weight.

## Hand-checking 50 shipped decisions caught 7 wrong admissions

The golden dataset was seeded from the pipeline's own committed outputs and then verified by hand against the raw records. That pass found the oncology protocol admitting patients its own lab criterion should have excluded: the evaluator resolved a criterion's field only through `field`/`type` and never `test_name`, so every lab criterion abstained with `no data for lab_result` while the HbA1c value sat loaded in the patient profile.

The abstention was polite, visible, and wrong, and because MAYBE counts half instead of disqualifying, it quietly inflated 7 of 25 oncology admissions: patients with HbA1c between 8.1 and 9.5 were reported eligible with confidence up to 0.94 against a protocol requiring less than 8.0.

One line fixed it, 25 criterion verdicts changed, 7 of 25 eligibility decisions flipped, and the re-verified outputs are the goldens CI now replays. The caveat, stated as loudly as the finding: these are 25 synthetic patients and one labeller, so the number that matters is not 7, it is that the audit machinery exists and runs on every push.

## The labels refuted my own thresholds

The semantic thresholds were supposed to be derived, not typed: hand-label exemplar (note, criterion) pairs, then require each named constant to sit inside the interval its labels imply. `evals/derive.py` is that claim, executable. It came back with a verdict I did not want:

```
GATE                                     VALUE  BELOW EDGE ABOVE EDGE  STATUS
SEMANTIC_PASS                             0.15        0.51       0.12  REFUTED
SEMANTIC_MAYBE                            0.10        0.51       0.10  REFUTED
COSINE_PASS                               0.10           -          -  AUTHORED

0 of 3 named gating thresholds are DERIVED from labelled exemplars.
```

A criterion with no support anywhere in the note scores 0.29. A criterion the note supports explicitly, 35 years of documented occupational exposure, scores 0.12. And the loudest row: "Must be non-smoker for at least 5 years" scores 0.51 on a patient whose note says active smoker, 18 pack-years, because cosine similarity sees the topic and cannot see the negation. No cutoff on that axis separates supported from unsupported: **0 of 3** thresholds derive, **2 refuted** by their own labels, 1 authored with no exemplar pair on its axis.

The response is not to hide the number. The refutation itself is pinned in `evals/derivation.expected.json` and guarded by CI: if a change silently makes the split look better or worse, the build goes red until the expectation is re-reviewed. The decision-level safety does not rest on these thresholds; it rests on the FAIL override and on abstention, which is exactly what the 17 labelled rows say it should.

## Architecture

<p align="center"><img src="assets/architecture.svg" alt="Data flow: protocol YAMLs, patient CSVs, and clinical notes are normalized into profiles and criteria, evaluated down a structured lane and a MiniLM semantic lane, and emitted as per-criterion verdicts with evidence strings and confidence; a golden-dataset gate replays all 50 decisions in CI" width="100%"></p>

Six small modules, one direction of flow. `protocol_sorter.py` repairs the protocol YAML (the source files ship with a dangling list, deliberately kept) and splits criteria into structured and unstructured. `data_loader.py` builds one profile per patient: age from calendar arithmetic, smoker flag, most-recent lab per test, note text. `protocol_evaluator.py` runs the structured comparisons; `note_parser.py` runs synonym shortcut, then MiniLM similarity, then a bag-of-words fallback. The orchestrator sorts eligible first by confidence and writes one JSON per protocol.

The embedding model loads lazily and the scorer is injectable, so the deterministic core imports and tests without torch installed. That seam is what keeps the CI checks job at zero model downloads.

## The gate CI actually runs

Free tier, no model, no network beyond pip. This is the literal `checks` job, and `make ci` runs the same commands locally:

```
python -m pytest -m "not slow" -v      # 41 tests over the deterministic core
python evals/suite.py --dry-run        # goldens: 50 decisions, closed verdict
                                       # vocabulary, confidence re-derivation,
                                       # any-FAIL invariant, input schemas
python evals/derive.py                 # thresholds vs labels, refutation pinned
python tools/readme_numbers.py --check # every counted number in this README
                                       # regenerates from its artifact
```

Model tier, the `eval-full` job: recompute all 50 decisions with the real MiniLM stack and compare to the goldens. Eligibility and per-criterion verdicts must match exactly; numeric scores get a 0.02 tolerance because embedding stacks differ across torch builds, and a real regression moves a verdict, not a third decimal. Last recorded run: **50 of 50** decisions agree, **17 of 17** labelled scores re-measured within tolerance (`evals/last_full_run.json`, committed).

The threshold derivation reads its exemplars from `evals/labels.csv`. Each row quotes the score the shipped output carries for that exact patient and criterion, and derive.py fails if any quoted score stops appearing verbatim, so a label cannot drift away from the artifact it cites.

## What measuring it taught

1. **The baseline can be the bug.** The committed outputs, the ground truth everything gets diffed against, carried mojibake: the normalizer wrote `≥` as `â‰¥` through a default-encoding write, and the corruption was baked into the regression baseline itself. First lesson of building the gate: verify the goldens before trusting the goldens.
2. **Polite abstention can hide a dead feature.** The lab gate never ran, and it never ran loudly enough to look correct: `MAYBE (no data for lab_result)` reads like caution, not breakage. 7 of 25 admissions were wrong. Abstention needs an eval that counts what abstains and asks why.
3. **A threshold you cannot derive is an opinion.** Labelling 17 exemplars took an evening and killed 2 of 3 thresholds. The honest state, 0 of 3 derived, now lives in CI as a pinned expectation instead of in my head as an intention.
4. **Small formulas rot quietly.** `days // 365` overstated a patient's age by one year, disagreeing with the age written in her own clinical note; the uppercase `CHF` synonym key was unreachable below a lowercasing lookup, so every CHF synonym was dead code. Both were caught by the first real test pass, neither changed a decision, both are the kind of thing that eventually does.

## The numbers

| what | value | how it is known |
| --- | --- | --- |
| decisions in the golden gate | 50 decisions, 25 patients x 2 protocols | `python evals/suite.py --dry-run` |
| criterion verdicts / abstentions | 550 / 67 abstentions, each naming its gap | same dry run, counted from the goldens |
| full-model agreement | 50 of 50 decisions, 17 of 17 label scores within 0.02 | `python evals/suite.py --full`, receipt committed |
| tests, model-free | 41 tests | `python -m pytest -m "not slow"` |
| thresholds derived / refuted | 0 of 3 derived, 2 refuted by their own labels | `python evals/derive.py` |
| wrong admissions caught | 7 of 25 oncology decisions flipped True to False | lab-gate fix, measured in the fixing commit's diff |
| bugs found while building the gate | 4 (encoding, lab gate, age drift, dead synonyms) | the commit history of this hardening pass |

`tools/readme_numbers.py --check` regenerates the first five rows from the artifacts they cite on every CI run; the last two are historical measurements recorded in their commits.

## What ships here, and what does not

Ships and runs on a fresh clone: the full pipeline, the tests, the golden gate, the threshold derivation, Docker and compose files, and all the data (25 synthetic patients, 2 protocols). Zero PHI by construction: every patient, note, and lab value is synthetic.

Not claimed: production traffic, clinician validation, or clinical validity of any decision. No LLM anywhere: this is classical NLP plus sentence embeddings, which is the honest tool for a pipeline whose selling point is that you can re-derive its every verdict by hand.

## Quick start

Free path first, no model download:

```bash
make setup        # venv + pinned deps + pytest
make test         # 41 tests, deterministic core only
make eval         # golden dry run + threshold derivation
```

The full pipeline (downloads the MiniLM model, ~60MB, on first run):

```bash
make run          # evaluate all 25 patients against both protocols
make eval-full    # recompute all 50 decisions against the goldens
```

Or containerized:

```bash
make docker-build
make docker-run
```

## What this cannot tell you

- Whether a patient is actually eligible. The data is synthetic and no clinician has reviewed the criteria logic. This repo demonstrates decision auditability, not clinical truth.
- Whether a note asserts or denies a concept. Cosine similarity is negation-blind, the 0.51 active-smoker row proves it, and absence-phrased criteria ("no personal history of malignancy") are matched by the very words they negate. Real clinical NLP needs negation handling and entity-level extraction; this instrument knows only nearness.
- Whether the thresholds generalize. They are refuted at n=17 labels from one labeller; more labels would move the edges, and the derivation harness exists precisely so that moving them is a measured act.

## Roadmap

- Drift monitoring on the semantic score distributions, designed but not running: the honest state is that nothing here watches production, because nothing here is in production.
- Negation-aware matching for absence-phrased criteria, evaluated against the same labels that refuted the current thresholds.
- A second labeller for `evals/labels.csv`, so the refutation carries inter-rater weight.
- A small Streamlit review UI for the MAYBE queue.

## Project structure

```
data/                 25 synthetic patients: demographics, labs, clinical notes
  protocol_*.yaml     2 trial protocols (raw + normalized _clean variants)
src/                  loader, protocol sorter, evaluator, note parser, orchestrator
tests/                41 model-free tests + 1 marked-slow real-model test
evals/
  golden/             all 50 expected decisions, hand-verified
  labels.csv          17 labelled exemplars, each citing a shipped score
  derive.py           thresholds vs labels, refutation pinned and guarded
  suite.py            --dry-run (free, CI) and --full (model recompute)
tools/readme_numbers.py   every counted number here, regenerated or failed
assets/               hand-authored SVGs, XML-checked in CI
output/               the shipped decision JSONs the goldens were seeded from
```

## License

Apache-2.0. NOTICE retained.
