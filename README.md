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
It is that hand-checking all 50 shipped decisions caught 7 wrong admissions,<br/>
and the gate that caught them now runs in CI, guarding even its own refuted thresholds.

<code>normalize -> compare -> abstain-or-decide -> explain</code>

</div>

---

## The 90 second tour

Every verdict ships with its evidence, and CI replays all 50 golden decisions plus the threshold audit on every push.

| if you want | go to |
| --- | --- |
| the decision a reviewer would audit | [Why the MAYBE verdict is the point](#why-the-maybe-verdict-is-the-point) |
| the bug the gate caught | [Hand-checking 50 shipped decisions caught 7 wrong admissions](#hand-checking-50-shipped-decisions-caught-7-wrong-admissions) |
| the claim the labels killed | [The labels refuted my own thresholds](#the-labels-refuted-my-own-thresholds) |
| the whole gate, free, in one command | [The gate CI actually runs](#the-gate-ci-actually-runs) |
| what is not claimed | [What this cannot tell you](#what-this-cannot-tell-you) |

## Why the MAYBE verdict is the point

A screening decision is one somebody else has to defend later. So the unit of output is a verdict with its receipt:

```
"HbA1c level must be less than 8.0%.":            "FAIL (HbA1c=8.1 not lt 8.0)"
"Patient must be between 50 and 70 years of age": "PASS (age=53 in range 50-70)"
"Spirometry FEV1 between 50-80% predicted.":      "MAYBE (no data for FEV1_percent)"
```

Three rules carry the safety weight:

- **Missing data abstains by name.** No FEV1 in the record yields `MAYBE (no data for FEV1_percent)`, never a silent pass. 67 of 550 shipped verdicts abstain, and each names its gap.
- **One FAIL disqualifies.** A patient with a disqualifying lab cannot be argued back in by strong matches elsewhere.
- **Confidence re-derives by hand.** It is the mean of PASS=1 and MAYBE=0.5. The dry-run gate recomputes every stored value from its own verdicts, so the formula cannot drift without CI noticing.

Unstructured criteria, like family history or occupational exposure, are matched against the clinical note with MiniLM embeddings, and the match score ships inside the evidence string. Similarity turned out to be a weak instrument. The refutation section below measures how weak.

## Hand-checking 50 shipped decisions caught 7 wrong admissions

The goldens were seeded from the pipeline's own outputs, then verified by hand against the raw records. That pass caught the oncology protocol admitting patients its lab criterion should have excluded.

The cause: the evaluator resolved a criterion's field through `field` and `type` but never `test_name`. Every lab criterion abstained with `no data for lab_result` while the HbA1c value sat loaded in the profile. MAYBE counts half instead of disqualifying, so the miss inflated 7 of 25 oncology admissions. Patients with HbA1c between 8.1 and 9.5 were reported eligible, at confidence up to 0.94, against a protocol requiring less than 8.0.

One line fixed it. 25 criterion verdicts changed, 7 eligibility decisions flipped, and the re-verified outputs are the goldens CI now replays. The caveat is real: 25 synthetic patients, one labeller. What lasts is not the 7, it is the audit that now runs on every push.

## The labels refuted my own thresholds

The semantic thresholds were supposed to be derived, not typed: label exemplar pairs by hand, then require each named constant to sit inside the interval its labels imply. `evals/derive.py` is that claim, executable. It came back with a verdict I did not want:

```
GATE                                     VALUE  BELOW EDGE ABOVE EDGE  STATUS
SEMANTIC_PASS                             0.15        0.51       0.12  REFUTED
SEMANTIC_MAYBE                            0.10        0.51       0.10  REFUTED
COSINE_PASS                               0.10           -          -  AUTHORED

0 of 3 named gating thresholds are DERIVED from labelled exemplars.
```

A criterion with no support anywhere in the note scores 0.29. A criterion the note supports explicitly, 35 years of documented occupational exposure, scores 0.12. The loudest row: "Must be non-smoker for at least 5 years" scores 0.51 on a patient whose note says active smoker, 18 pack-years. Cosine similarity sees the topic and cannot see the negation.

So no cutoff on that axis separates supported from unsupported. The split is pinned rather than hidden: `evals/derivation.expected.json` records 0 of 3 derived, and CI goes red if it moves either way without a re-review. Decision safety rests on the FAIL override and on abstention, which is what the labelled rows recommend.

## Architecture

<p align="center"><img src="assets/architecture.svg" alt="Data flow: protocol YAMLs, patient CSVs, and clinical notes are normalized into profiles and criteria, evaluated down a structured lane and a MiniLM semantic lane, and emitted as per-criterion verdicts with evidence strings and confidence; a golden-dataset gate replays all 50 decisions in CI" width="100%"></p>

Six small modules, one direction of flow, and a gate underneath the whole thing.

<details>
<summary>Mermaid source for this diagram</summary>

```mermaid
%%{init: {"theme": "base", "themeVariables": {
  "fontSize": "16px",
  "primaryColor": "#0c1013", "primaryTextColor": "#e6eae8", "primaryBorderColor": "#46555f",
  "lineColor": "#7a8691", "textColor": "#b8c0bd",
  "clusterBkg": "#223140", "clusterBorder": "#3d4f5e",
  "edgeLabelBackground": "#0c1013", "tertiaryColor": "#223140"
}}}%%
flowchart TD
    subgraph IN [inputs]
        P["protocol YAMLs"]
        C["patients.csv + labs.csv"]
        N["25 clinical notes"]
    end
    S["protocol_sorter.py<br/>repair + split criteria"]
    L["data_loader.py<br/>one profile per patient"]
    subgraph EV [evaluate]
        E["structured lane<br/>age, flags, labs"]
        M["semantic lane<br/>MiniLM matching"]
    end
    V["PASS / MAYBE / FAIL per criterion<br/>evidence string + score"]
    O["orchestrator.py<br/>confidence, sort, JSON"]
    G["the gate: 50 golden decisions<br/>replayed in CI"]

    P --> S
    C --> L
    N --> L
    S --> EV
    L --> EV
    E --> V
    M --> V
    V --> O
    O --> G

    classDef gate fill:#10201d,stroke:#2dd4bf,color:#5eead4,stroke-width:1.5px
    class G gate
```

</details>

`protocol_sorter.py` repairs the protocol YAML and splits criteria into structured and unstructured. (The source files ship with a dangling list, deliberately kept.) `data_loader.py` builds one profile per patient: age from calendar arithmetic, smoker flag, most-recent lab per test, note text. `protocol_evaluator.py` runs the structured comparisons. `note_parser.py` tries a synonym shortcut, then MiniLM similarity, then a bag-of-words fallback. The orchestrator sorts eligible patients first by confidence and writes one JSON per protocol.

The embedding model loads lazily and the scorer is injectable. The deterministic core imports and tests without torch installed, which keeps the CI checks job at zero model downloads.

## The gate CI actually runs

Free tier first: no model, no network beyond pip. The `checks` job runs these commands, and `make ci` runs the same ones locally:

```
python -m pytest -m "not slow" -v      # 41 tests over the deterministic core
python evals/suite.py --dry-run        # goldens: 50 decisions, closed verdict
                                       # vocabulary, confidence re-derivation,
                                       # any-FAIL invariant, input schemas
python evals/derive.py                 # thresholds vs labels, refutation pinned
python tools/readme_numbers.py --check # every counted number in this README
                                       # regenerates from its artifact
```

The `eval-full` job recomputes all 50 decisions with the real MiniLM stack. Eligibility and per-criterion verdicts must match the goldens exactly. Scores get a 0.02 tolerance, because embedding stacks differ across torch builds and a real regression moves a verdict, not a third decimal. Last recorded run: 50 of 50 decisions agree, 17 of 17 labelled scores re-measured within tolerance (`evals/last_full_run.json`, committed).

Threshold exemplars live in `evals/labels.csv`. Each row quotes the score the shipped output carries for that patient and criterion, and derive.py fails if any quoted score stops appearing verbatim. A label cannot drift from the artifact it cites.

## What measuring it taught

1. **The baseline can be the bug.** The committed outputs carried mojibake: the normalizer wrote `≥` as `â‰¥` through a default-encoding write, and the corruption sat inside the regression baseline itself. Verify the goldens before trusting the goldens.
2. **Polite abstention can hide a dead feature.** The lab gate never ran, and `MAYBE (no data for lab_result)` read like caution rather than breakage. 7 of 25 admissions were wrong. Count what abstains, and ask why.
3. **A threshold you cannot derive is an opinion.** Labelling 17 exemplars took an evening and killed 2 of 3 thresholds. The result now lives in CI as a pinned expectation instead of in my head as an intention.
4. **Small formulas rot quietly.** `days // 365` overstated a patient's age by one year against her own clinical note. An uppercase `CHF` synonym key sat unreachable below a lowercasing lookup. The first real test pass caught both. Neither changed a decision; both are the kind that eventually does.

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

`tools/readme_numbers.py --check` regenerates the first five rows from their artifacts on every CI run. The last two are historical measurements, recorded in their commits.

## What ships here, and what does not

Everything runs on a fresh clone: pipeline, tests, golden gate, threshold derivation, Docker files, and all the data. Zero PHI by construction: every patient, note, and lab value is synthetic.

Not claimed: production traffic, clinician validation, or clinical validity of any decision. No LLM anywhere. Classical NLP plus sentence embeddings, chosen so every verdict stays re-derivable by hand.

## Quick start

Needs python3 and make. Docker is optional, and the ~60MB model download happens only on the full paths.

Free path, no model:

```bash
make setup        # venv + pinned deps + pytest
make test         # 41 tests, deterministic core only
make eval         # golden dry run + threshold derivation
```

Full pipeline:

```bash
make run          # evaluate all 25 patients against both protocols
make eval-full    # recompute all 50 decisions against the goldens
```

Containerized:

```bash
make docker-build
make docker-run
```

## What this cannot tell you

- Whether a patient is actually eligible. The data is synthetic and no clinician has reviewed the criteria logic. This repo demonstrates decision auditability, not clinical truth.
- Whether a note asserts or denies a concept. Cosine similarity is negation-blind; the 0.51 active-smoker row proves it. Absence criteria, like "no personal history of malignancy", are matched by the very words they negate.
- Whether the thresholds generalize. They are refuted at 17 labels from one labeller. More labels would move the edges, and the harness exists so that moving them is a measured act.

## Roadmap

- Drift monitoring on the score distributions. Nothing here watches production, because nothing here is in production.
- Negation-aware matching, evaluated against the same labels that refuted the current thresholds.
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
