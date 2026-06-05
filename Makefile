.PHONY: dev clean

dev:
	uv sync

clean:
	rm -rf .venv
