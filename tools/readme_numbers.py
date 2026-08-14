#!/usr/bin/env python3
"""Every counted number the README asserts, regenerated from the artifact it
cites. `--check` fails when the README and the artifacts disagree, which is
how a number stays a measurement instead of decaying into a typo.

    python3 tools/readme_numbers.py --json    # print the numbers
    python3 tools/readme_numbers.py --check   # assert the README carries them
"""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
README = os.path.join(ROOT, "README.md")


def verdicts(golden):
    for patients in golden.values():
        for rec in patients:
            for ev in rec["evidence"].values():
                yield ev.split(" ")[0]


def compute():
    n = {}
    golden = {}
    for proto in ("ONC-003-Prevention", "RESP-005-Cessation"):
        path = os.path.join(ROOT, "evals", "golden", f"{proto}.expected.json")
        with open(path, encoding="utf-8") as fh:
            golden[proto] = json.load(fh)
    n["decisions"] = sum(len(v) for v in golden.values())
    vs = list(verdicts(golden))
    n["criterion_verdicts"] = len(vs)
    n["abstentions"] = vs.count("MAYBE")
    n["eligible"] = sum(
        1 for patients in golden.values() for rec in patients
        if rec["is_eligible"] is True)

    with open(os.path.join(ROOT, "evals", "labels.csv"), encoding="utf-8") as fh:
        body = [ln for ln in fh if ln.strip() and not ln.lstrip().startswith("#")]
    n["labels"] = max(0, len(body) - 1)

    derive = subprocess.run(
        [sys.executable, os.path.join(ROOT, "evals", "derive.py"), "--json"],
        capture_output=True, text=True)
    d = json.loads(derive.stdout)
    n["derived"] = d["derived"]
    n["named_gates"] = d["n_gating"]
    n["refuted"] = d["refuted"]

    receipt_path = os.path.join(ROOT, "evals", "last_full_run.json")
    with open(receipt_path, encoding="utf-8") as fh:
        receipt = json.load(fh)
    n["agree"] = receipt["agree"]
    if receipt["decisions"] != n["decisions"]:
        raise SystemExit(
            f"receipt says {receipt['decisions']} decisions, goldens say "
            f"{n['decisions']}; rerun evals/suite.py --full")

    collect = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-m", "not slow"],
        capture_output=True, text=True, cwd=ROOT)
    n["tests"] = sum(
        1 for ln in collect.stdout.splitlines() if "::" in ln and " " not in ln.strip())
    return n


def needles(n):
    return [
        f"{n['decisions']} decisions",
        f"{n['abstentions']} abstention",
        f"{n['tests']} tests",
        f"{n['derived']} of {n['named_gates']}",
        f"{n['refuted']} refuted",
        f"{n['agree']} of {n['decisions']}",
        f"tests-{n['tests']}_passing",
        f"decisions-{n['decisions']}",
        f"agreement-{n['agree']}%2F{n['decisions']}",
        f"abstains-{n['abstentions']}",
        f"thresholds-{n['derived']}%2F{n['named_gates']}",
    ]


def main():
    n = compute()
    if "--json" in sys.argv:
        print(json.dumps(n, indent=2))
        return 0
    with open(README, encoding="utf-8") as fh:
        text = fh.read()
    missing = [needle for needle in needles(n) if needle not in text]
    for needle in needles(n):
        print(("ok      " if needle in text else "MISSING ") + needle)
    if missing:
        print(f"\n{len(missing)} README number(s) do not match the artifacts. "
              f"Regenerate the claim or rerun the measurement.")
        return 1
    print("\nevery counted README number regenerates from its artifact")
    return 0


if __name__ == "__main__":
    sys.exit(main())
