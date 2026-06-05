VENV := .venv
PYTHON := $(VENV)/bin/python
PYBOX_ROOT := $(shell cd ../.. && pwd)
# Absolute path to the venv so the attack script can locate it regardless of CWD
VENV_ABS := $(shell pwd)/.venv

.PHONY: setup attack clean

setup:
	uv venv $(VENV)
	uv pip install --quiet --python $(PYTHON) $(PYBOX_ROOT) requests
	$(PYTHON) -c "import pybox; print('pybox', pybox.__version__)"
	@echo "Setup complete. python -> $$(readlink $(VENV)/bin/python)"

attack: setup
	@# Run the attack from a workspace subdirectory so the venv is NOT inside
	@# the sandboxed process's working directory. This mirrors real-world usage
	@# where the venv lives outside the agent's project tree.
	mkdir -p workspace
	cp attack.py workspace/attack.py
	cd workspace && ../$(PYTHON) attack.py --venv $(VENV_ABS)

clean:
	rm -rf $(VENV) workspace __pycache__
