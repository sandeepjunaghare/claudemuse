PY = ../../.venv/bin/python
PYTHONPATH = src/review

.PHONY: install ci-review test test-unit test-integration test-gen metrics

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

# Phase 2/3 targets — not implemented yet.
test-gen:
	@echo "test-gen: not implemented (Phase 3)"

metrics:
	@echo "metrics: not implemented (Phase 2)"
