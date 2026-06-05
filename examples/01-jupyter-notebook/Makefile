VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
PYBOX_ROOT := $(shell cd ../.. && pwd)
SENTINEL := $(VENV)/bin/pybox_launcher

.PHONY: setup run serve clean

setup: $(SENTINEL)

$(SENTINEL):
	python3.14 -m venv $(VENV)
	$(PIP) install --quiet $(PYBOX_ROOT) jupyter ipykernel pandas matplotlib
	$(PYTHON) -c "import pybox; print('pybox', pybox.__version__)"
	@echo ""
	@echo "Setup complete. Sandbox wrappers installed."
	@echo "  python -> $$(readlink $(VENV)/bin/python)"

run: $(SENTINEL)
	mkdir -p output
	$(PYTHON) -m jupyter nbconvert \
		--to notebook \
		--execute analysis.ipynb \
		--output output/executed.ipynb \
		--ExecutePreprocessor.timeout=60
	$(PYTHON) -m jupyter nbconvert \
		--to html \
		output/executed.ipynb \
		--output report.html
	@echo ""
	@echo "Notebook executed. Open output/report.html to review results."

serve: $(SENTINEL)
	@echo "Starting Jupyter. Press Ctrl-C to stop."
	$(PYTHON) -m jupyter notebook --port 8888 analysis.ipynb

clean:
	rm -rf $(VENV) output __pycache__ .ipynb_checkpoints
