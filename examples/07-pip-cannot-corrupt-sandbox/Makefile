VENV := .venv
PYTHON := $(VENV)/bin/python
WRAPPER := $(VENV)/bin/pybox_wrapper.sh

.PHONY: setup attack clean

setup:
	python -m venv $(VENV)
	$(VENV)/bin/pip install --quiet pybox
	$(PYTHON) -c "import pybox; print('pybox', pybox.__version__)"
	@echo "Setup complete. python -> $$(readlink $(VENV)/bin/python)"

attack: setup
	@echo "--- Recording wrapper checksum before attack ---"
	$(eval BEFORE := $(shell shasum -a 256 $(WRAPPER) | awk '{print $$1}'))
	@echo "  $(WRAPPER): $(BEFORE)"
	@echo ""
	@echo "--- Installing malicious package via sandboxed pip ---"
	$(VENV)/bin/pip install ./malicious_pkg
	@echo ""
	@echo "--- Verifying wrapper is unchanged ---"
	$(eval AFTER := $(shell shasum -a 256 $(WRAPPER) | awk '{print $$1}'))
	@echo "  $(WRAPPER): $(AFTER)"
	@test "$(BEFORE)" = "$(AFTER)" \
		&& echo "PASS: wrapper checksum unchanged" \
		|| (echo "FAIL: wrapper was modified!" && exit 1)
	@echo ""
	@echo "--- Confirming sandbox still works ---"
	$(PYTHON) verify.py

clean:
	rm -rf $(VENV) malicious_pkg/__pycache__ malicious_pkg/*.egg-info __pycache__
