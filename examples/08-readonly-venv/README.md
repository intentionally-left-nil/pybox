# Example: Read-only Venv

This example demonstrates that a sandboxed Python process can *read* from its
own venv (import packages, read library files) but cannot *modify* it — even
though the venv tree is well within reach.

## The attack idea

The venv is typically located alongside the project directory. A misbehaving
agent might try to:

- Inject a malicious `.pth` file into `site-packages` (executed on every Python
  startup, giving persistent code execution)
- Delete or corrupt a library it dislikes
- Write a backdoored `__init__.py` into an installed package

## Why it does not work

The pybox python sandbox profile grants:

- **Read** access to the entire venv tree (so imports work)
- **Write** access only to `<venv>/__pycache__` (for `.pyc` files)
- The working directory gets full read/write

Everything else in the venv — `lib/`, `site-packages/`, `bin/` — is
effectively read-only from the sandbox's perspective.

## What it checks

| Attack | Target | Expected result |
|--------|--------|-----------------|
| Inject `.pth` file | `<venv>/lib/pythonX.Y/site-packages/evil.pth` | `PermissionError` |
| Delete a library | `<venv>/lib/pythonX.Y/site-packages/requests/__init__.py` | `PermissionError` |
| Overwrite a package file | `<venv>/lib/pythonX.Y/site-packages/requests/__init__.py` | `PermissionError` |
| Write to venv root | `<venv>/injected.txt` | `PermissionError` |

Importing `requests` after all attacks confirms the package is undamaged.

## Setup

Uses a `uv`-based venv.

```
uv venv .venv
uv pip install pybox requests
```

## File layout

```
08-readonly-venv/
├── README.md
├── Makefile
└── attack.py    # Attempts all venv-modification attacks, then imports requests
```

## Make targets

| Target | Description |
|--------|-------------|
| `make setup` | Create venv, install pybox + requests |
| `make attack` | Run all venv-tampering attacks, verify venv is intact |
| `make clean` | Remove venv |

## Expected output

All attack attempts raise `PermissionError`. The final `import requests` check
succeeds, confirming the venv is undamaged.
