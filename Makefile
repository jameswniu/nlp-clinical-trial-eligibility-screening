# Every target the CI workflow runs exists here first, so local and CI are the
# same commands. The free path (test, eval) needs no model download and no torch.

VENV = .venv
BIN = $(VENV)/bin
# Prefer the project venv once `make setup` has created it, so every target
# sees pytest and the pinned deps without activation.
PY ?= $(shell [ -x $(BIN)/python ] && echo $(BIN)/python || echo python3)

.PHONY: setup run test test-slow eval eval-full readme-check svg-check ci docker-build docker-run clean

setup:
	$(PY) -m venv $(VENV)
	$(BIN)/pip install --upgrade pip
	$(BIN)/pip install -r requirements.txt
	$(BIN)/pip install pytest

run:
	$(PY) src/orchestrator.py

test:
	$(PY) -m pytest -m "not slow" -q

test-slow:
	$(PY) -m pytest -m slow -q

eval:
	$(PY) evals/suite.py --dry-run
	$(PY) evals/derive.py

eval-full:
	$(PY) evals/suite.py --full

readme-check:
	$(PY) tools/readme_numbers.py --check

svg-check:
	$(PY) -c "import xml.etree.ElementTree as ET, glob; files = glob.glob('assets/*.svg'); assert files, 'no SVGs found'; [ET.parse(f) for f in files]; print(f'{len(files)} SVGs parse as XML')"

# The exact free gate CI runs, in the same order.
ci: test eval readme-check svg-check

docker-build:
	docker build -t clinical-trial-screening .

docker-run:
	docker run --rm \
	  -v $(PWD)/data:/app/data \
	  -v $(PWD)/output:/app/output \
	  clinical-trial-screening

clean:
	rm -rf .pytest_cache src/__pycache__ tests/__pycache__ evals/__pycache__
