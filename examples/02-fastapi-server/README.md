# Example: FastAPI Server

This example demonstrates that a FastAPI web server starts and serves requests
normally inside the pybox sandbox. Network I/O is unrestricted by default —
pybox only restricts filesystem access.

## What it checks

- `uvicorn` binds to a port and serves HTTP requests correctly
- The server can read its configuration from the working directory
- Request handlers can read and write files in the working directory
- Request handlers **cannot** write to paths outside the working directory
- The sandbox does not interfere with Python's networking stack

## Setup

Uses a `uv`-based venv.

```
uv venv .venv
uv pip install pybox fastapi uvicorn httpx
```

## File layout

```
02-fastapi-server/
├── README.md
├── Makefile
├── app.py           # FastAPI application
├── logs/            # Server writes request logs here (in CWD, allowed)
└── .gitignore
```

## Make targets

| Target | Description |
|--------|-------------|
| `make setup` | Create venv, install dependencies |
| `make serve` | Start uvicorn in the foreground (interactive) |
| `make test` | Start server in background, run curl tests, stop server |
| `make clean` | Remove venv and logs |

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Health check |
| `GET` | `/items/{id}` | Return a mock item |
| `POST` | `/log` | Append a message to `logs/requests.log` (in CWD — allowed) |
| `POST` | `/escape` | Attempt to write to `/tmp/escaped.txt` — blocked, returns 500 with the error |

## Expected behaviour

`make test` runs four requests. The first three succeed. The `/escape` request
returns HTTP 500 and the response body contains `PermissionError`, proving the
sandbox blocked the out-of-bounds write without crashing the server.
