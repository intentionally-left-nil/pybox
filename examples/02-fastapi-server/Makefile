VENV := .venv
PYTHON := $(VENV)/bin/python
UVICORN := $(VENV)/bin/uvicorn
HOST := 127.0.0.1
PORT := 8000

.PHONY: setup serve test clean

setup:
	uv venv $(VENV)
	uv pip install --quiet --python $(PYTHON) pybox fastapi uvicorn httpx
	$(PYTHON) -c "import pybox; print('pybox', pybox.__version__)"
	@echo ""
	@echo "Setup complete."
	@echo "  python -> $$(readlink $(VENV)/bin/python)"

serve: setup
	@echo "Starting FastAPI server at http://$(HOST):$(PORT)"
	@echo "Press Ctrl-C to stop."
	$(UVICORN) app:app --host $(HOST) --port $(PORT) --reload

test: setup
	@echo "--- Starting server in background ---"
	$(UVICORN) app:app --host $(HOST) --port $(PORT) &
	@sleep 2
	@echo ""
	@echo "--- GET / (health check) ---"
	curl -sf http://$(HOST):$(PORT)/ | python3 -m json.tool
	@echo ""
	@echo "--- GET /items/42 ---"
	curl -sf http://$(HOST):$(PORT)/items/42 | python3 -m json.tool
	@echo ""
	@echo "--- POST /log (write inside CWD — should succeed) ---"
	curl -sf -X POST http://$(HOST):$(PORT)/log \
		-H 'Content-Type: application/json' \
		-d '{"message": "hello from curl"}' | python3 -m json.tool
	@echo ""
	@echo "--- POST /escape (write outside CWD — should be blocked) ---"
	curl -s -X POST http://$(HOST):$(PORT)/escape | python3 -m json.tool || true
	@echo ""
	@echo "--- Stopping server ---"
	-pkill -f "uvicorn app:app" 2>/dev/null || true
	@echo ""
	@echo "--- Log written inside CWD ---"
	cat logs/requests.log

clean:
	-pkill -f "uvicorn app:app" 2>/dev/null || true
	rm -rf $(VENV) logs __pycache__
