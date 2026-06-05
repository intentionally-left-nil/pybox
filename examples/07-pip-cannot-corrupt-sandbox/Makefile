VENV := .venv
PYTHON := $(VENV)/bin/python
LAUNCHER := $(VENV)/bin/pybox_launcher
PYBOX_ROOT := $(shell cd ../.. && pwd)

.PHONY: setup attack clean

setup:
	uv venv --seed $(VENV)
	uv pip install --quiet --python $(PYTHON) $(PYBOX_ROOT)
	$(PYTHON) -c "import pybox; print('pybox', pybox.__version__)"
	@echo "Setup complete. python -> $$(readlink $(VENV)/bin/python)"

attack: setup
	@echo "--- Recording launcher checksum before attack ---"
	$(eval BEFORE := $(shell shasum -a 256 $(LAUNCHER) | awk '{print $$1}'))
	@echo "  $(LAUNCHER): $(BEFORE)"
	@echo ""
	@echo "--- Installing malicious package via sandboxed pip ---"
	$(VENV)/bin/pip install ./malicious_pkg
	@echo ""
	@echo "--- Verifying launcher is unchanged ---"
	$(eval AFTER := $(shell shasum -a 256 $(LAUNCHER) | awk '{print $$1}'))
	@echo "  $(LAUNCHER): $(AFTER)"
	@test "$(BEFORE)" = "$(AFTER)" \
		&& echo "PASS: launcher checksum unchanged" \
		|| (echo "FAIL: launcher was modified!" && exit 1)
	@echo ""
	@echo "--- Confirming sandbox still works ---"
	$(PYTHON) verify.py

clean:
	rm -rf $(VENV) malicious_pkg/__pycache__ malicious_pkg/*.egg-info __pycache__
