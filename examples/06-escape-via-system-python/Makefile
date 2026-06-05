VENV := .venv
PYTHON := $(VENV)/bin/python
SENTINEL := /tmp/pybox-escape-sentinel.txt

.PHONY: setup escape clean

setup:
	uv venv $(VENV)
	uv pip install --quiet --python $(PYTHON) pybox
	$(PYTHON) -c "import pybox; print('pybox', pybox.__version__)"
	@echo "Setup complete. python -> $$(readlink $(VENV)/bin/python)"

escape: setup
	@echo "--- Creating sentinel file outside the sandbox ---"
	echo "do not touch" > $(SENTINEL)
	@echo "Sentinel: $(SENTINEL)"
	@echo ""
	@echo "--- Running escape attempts ---"
	$(PYTHON) escape.py --sentinel $(SENTINEL)
	@echo ""
	@echo "--- Verifying sentinel is intact ---"
	@test -f $(SENTINEL) \
		&& echo "PASS: sentinel still exists" \
		|| (echo "FAIL: sentinel was deleted" && exit 1)
	@test "$$(cat $(SENTINEL))" = "do not touch" \
		&& echo "PASS: sentinel content unchanged" \
		|| (echo "FAIL: sentinel was modified" && exit 1)
	@echo ""
	@echo "No escape succeeded. Process tree sandbox held."

clean:
	rm -rf $(VENV) __pycache__
	-rm -f $(SENTINEL)
