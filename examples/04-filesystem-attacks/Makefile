VENV := .venv
PYTHON := $(VENV)/bin/python
SENTINEL := /tmp/pybox-sentinel.txt
SENTINEL2 := /tmp/pybox-sentinel2.txt
PYBOX_ROOT := $(shell cd ../.. && pwd)

.PHONY: setup attack clean

setup:
	uv venv $(VENV)
	uv pip install --quiet --python $(PYTHON) $(PYBOX_ROOT)
	$(PYTHON) -c "import pybox; print('pybox', pybox.__version__)"
	@echo "Setup complete. python -> $$(readlink $(VENV)/bin/python)"

attack: setup
	@echo "--- Creating sentinel files outside the sandbox ---"
	echo "important data" > $(SENTINEL)
	echo "also important" > $(SENTINEL2)
	@echo "Sentinel 1: $(SENTINEL)"
	@echo "Sentinel 2: $(SENTINEL2)"
	@echo ""
	@echo "--- Running filesystem attack scenarios ---"
	$(PYTHON) attack.py
	@echo ""
	@echo "--- Verifying sentinels are intact ---"
	@test -f $(SENTINEL) && echo "PASS: $(SENTINEL) still exists" \
		|| (echo "FAIL: $(SENTINEL) was deleted" && exit 1)
	@test "$$(cat $(SENTINEL))" = "important data" \
		&& echo "PASS: $(SENTINEL) content unchanged" \
		|| (echo "FAIL: $(SENTINEL) content was modified" && exit 1)
	@test -f $(SENTINEL2) && echo "PASS: $(SENTINEL2) still exists" \
		|| (echo "FAIL: $(SENTINEL2) was deleted" && exit 1)
	@echo ""
	@echo "All sentinels intact. Sandbox held."

clean:
	rm -rf $(VENV) __pycache__
	-rm -f $(SENTINEL) $(SENTINEL2)
