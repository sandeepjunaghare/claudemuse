PY = ../../.venv/bin/python
PYTHONPATH = src/review

.PHONY: install ci-review test test-unit test-integration test-gen metrics tr3-demo review-multi dedupe-demo

install:
	$(PY) -m pip install -r requirements.txt

# Usage: make ci-review PR=fixtures/pr-01/sample.diff
ci-review:
	PYTHONPATH=$(PYTHONPATH) $(PY) -m cli --diff $(PR)

test: test-unit

test-unit:
	$(PY) -m pytest -m "not integration" -q

test-integration:
	$(PY) -m pytest -m integration -q

# Phase 3 target — not implemented yet.
test-gen:
	@echo "test-gen: not implemented (Phase 3)"

# metrics / tr3-demo make LIVE claude -p calls (need CLI + ANTHROPIC_API_KEY;
# haiku tier). They are effectively integration targets and are NOT run by
# `make test`.
metrics:
	PYTHONPATH=$(PYTHONPATH) $(PY) -c "import metrics; metrics.run_metrics()"

tr3-demo:
	PYTHONPATH=$(PYTHONPATH) $(PY) -c "import metrics; metrics.run_tr3_demo()"

# review-multi / dedupe-demo make LIVE, MULTI-pass claude -p calls (need CLI +
# ANTHROPIC_API_KEY; haiku tier). review-multi = N per-file passes + 1
# integration pass = N+1 model calls; dedupe-demo runs multipass TWICE. Higher
# cost than the single-pass demos; NOT run by `make test`.
review-multi:
	PYTHONPATH=$(PYTHONPATH) $(PY) -c "import multipass; multipass.run_multipass_demo()"

dedupe-demo:
	PYTHONPATH=$(PYTHONPATH) $(PY) -c "import multipass; multipass.run_dedupe_demo()"
