# Example: pip Cannot Corrupt the Sandbox

This example demonstrates that a malicious `pip install` cannot overwrite the
pybox wrapper scripts or the real Python binary — even though pip *does* have
write access to `<venv>/bin/` for installing legitimate console scripts.

## The attack idea

pybox's pip sandbox grants write access to `<venv>/bin/` so that `pip install`
can create new console-script entrypoints (e.g. `bin/pytest`, `bin/black`).
A malicious package could try to exploit this by writing a post-install hook
that overwrites `bin/pybox_wrapper.sh` or `bin/nosandbox/python` — replacing
the sandbox wrapper with a plain passthrough, or backdooring the interpreter.

## Why it does not work

The pip sandbox profile explicitly denies writes to specific critical paths
inside `<venv>/bin/`, even though the parent directory is writable:

- `<venv>/bin/python`
- `<venv>/bin/python3`
- `<venv>/bin/python3.X` (all version aliases)
- `<venv>/bin/pybox_wrapper.sh`
- `<venv>/bin/pybox_pip_wrapper.sh`
- `<venv>/bin/nosandbox/` (entire directory)

nono's `filesystem.deny` wins over a parent directory's write grant, and it
also blocks *creation* of non-existent files at those paths (not just writes to
existing ones).

## What it checks

A local package (`malicious_pkg`) is installed via `pip install ./malicious_pkg`.
Its `pyproject.toml` includes a post-install script that attempts to:

1. Overwrite `bin/pybox_wrapper.sh` with a no-op shell script
2. Overwrite `bin/nosandbox/python` symlink with a different interpreter
3. Write a new file named `bin/python` (which does not exist, as it is a symlink)

All three attempts raise `PermissionError`. The wrappers are intact after the
install, and the sandbox continues to function correctly.

## Setup

Uses a `pip`-based venv.

```
python -m venv .venv
pip install pybox
```

## File layout

```
07-pip-cannot-corrupt-sandbox/
├── README.md
├── Makefile
├── verify.py             # Checks wrappers are intact and sandbox still works
└── malicious_pkg/
    ├── pyproject.toml    # Package definition with post-install hook
    └── malicious_pkg/
        ├── __init__.py
        └── _install_hook.py   # The malicious post-install code
```

## Make targets

| Target | Description |
|--------|-------------|
| `make setup` | Create venv, install pybox |
| `make attack` | pip install the malicious package, verify wrappers intact |
| `make clean` | Remove venv |

## Expected output

The malicious package installs (its Python code lands in site-packages). But
every attempt to overwrite or tamper with the sandbox wrappers fails with
`PermissionError`. `make attack` confirms the wrappers are unchanged and that
`python -c "print('sandbox still works')"` executes correctly.
