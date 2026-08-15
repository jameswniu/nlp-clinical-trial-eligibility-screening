#!/usr/bin/env python3
"""Generate the 1,000-patient throughput cohort, deterministically.

This cohort exists to measure speed and memory at EHR-query scale, never to
carry golden verdicts: notes are templated (seeded PRNG, no LLM, no network),
so the corpus regenerates byte-identically from this script and is not
committed. The golden tiers are the 25 verified patients in data/ and the 175
audited patients in cohort/; this one is disposable by design.

    python3 bench/generate.py            # writes bench/corpus/ (gitignored)
    python3 bench/generate.py --n 1000 --seed 42
"""
import argparse
import csv
import os
import random

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "bench", "corpus")

CONDITIONS = [
    ("Type 2 Diabetes diagnosed in {yr}", True),
    ("no history of diabetes mellitus", False),
    ("long-standing Type 2 Diabetes with neuropathy", True),
]
SMOKE = [
    ("Never smoked tobacco.", False),
    ("Active smoker, about {cigs} cigarettes daily for {yrs} years.", True),
    ("Former smoker, quit {q} years ago.", False),
    ("Current smoker with multiple failed quit attempts.", True),
]
FAMILY = [
    "Family history includes mother with breast cancer.",
    "No known family history of cancer.",
    "Father had lung cancer; brother has diabetes.",
    "Family history unremarkable.",
]
EXTRAS = [
    "Cardiovascular examination unremarkable.",
    "Reports occupational exposure to dust and fumes for {yrs} years.",
    "Denies any occupational or environmental smoke exposure.",
    "Lives with supportive spouse.",
    "Lives alone, limited local support.",
    "Motivation to quit rated {mot}/10.",
    "Two quit attempts in the past three years.",
    "Last colonoscopy in {yr}.",
    "Never completed age-appropriate cancer screening.",
    "Drinks a glass of wine most evenings.",
    "No current medications beyond Metformin.",
]


def build(rng, i):
    pid = f"patient_B{i:04d}"
    age = rng.randint(30, 82)
    birth_year = 2024 - age
    dob = f"{birth_year}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}"
    gender = rng.choice(["Male", "Female"])
    smoke_line, is_smoker = rng.choice(SMOKE)
    smoke_line = smoke_line.format(cigs=rng.randint(5, 40), yrs=rng.randint(5, 40),
                                   q=rng.randint(2, 25))
    cond_line, _diabetic = rng.choice(CONDITIONS)
    cond_line = cond_line.format(yr=rng.randint(2010, 2023))

    labs = []
    if rng.random() < 0.85:
        for d in sorted(rng.sample(["2023-02-10", "2023-07-05", "2023-11-20",
                                    "2024-01-15", "2024-03-12"], rng.randint(1, 3))):
            labs.append((pid, "HbA1c", round(rng.uniform(5.4, 9.8), 1), "%", d))
    if rng.random() < 0.4:
        labs.append((pid, "FEV1_percent", rng.randint(38, 95), "%pred", "2024-02-01"))

    hba_line = ""
    if labs and labs[0][1] == "HbA1c":
        latest = [l for l in labs if l[1] == "HbA1c"][-1]
        hba_line = f"Recent HbA1c was {latest[2]}%."
    extras = rng.sample(EXTRAS, rng.randint(3, 5))
    extras = [e.format(yrs=rng.randint(5, 35), mot=rng.randint(1, 10),
                       yr=rng.randint(2015, 2023)) for e in extras]
    note = " ".join([
        f"Patient B{i:04d}, {gender}, {age} years old. DOB {dob}.",
        cond_line + ".", hba_line, smoke_line] + extras).replace("  ", " ")

    row = (pid, dob, gender, str(is_smoker).upper(),
           rng.choice(["high_school", "college", "some_college", ""]),
           rng.choice(["commercial", "medicare", "medicaid"]))
    return row, labs, (pid, note)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    rng = random.Random(args.seed)

    notes_dir = os.path.join(OUT, "clinical_notes")
    os.makedirs(notes_dir, exist_ok=True)
    rows, labrows = [], []
    for i in range(1, args.n + 1):
        row, labs, (pid, note) = build(rng, i)
        rows.append(row)
        labrows.extend(labs)
        with open(os.path.join(notes_dir, f"{pid}.txt"), "w", encoding="utf-8") as fh:
            fh.write(note + "\n")

    with open(os.path.join(OUT, "patients.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["patient_id", "date_of_birth", "gender", "is_smoker",
                    "education_level", "insurance_type"])
        w.writerows(rows)
    with open(os.path.join(OUT, "lab_results.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["patient_id", "lab_test_name", "value", "unit", "observation_date"])
        w.writerows(labrows)
    print(f"wrote {args.n} patients, {len(labrows)} lab rows, seed={args.seed} -> {OUT}")


if __name__ == "__main__":
    main()
