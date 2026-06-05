VENV := .venv
PYTHON := $(VENV)/bin/python

.PHONY: setup attack clean

setup:
	uv venv $(VENV)
	uv pip install --quiet --python $(PYTHON) pybox requests
	$(PYTHON) -c "import pybox; print('pybox', pybox.__version__)"
	@echo "Setup complete. python -> $$(readlink $(VENV)/bin/python)"

attack: setup
	$(PYTHON) attack.py --venv $(VENV)

clean:
	rm -rf $(VENV) __pycache__
