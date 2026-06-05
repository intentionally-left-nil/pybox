# Example: Filesystem Attacks

This example demonstrates that the pybox sandbox blocks all attempts by a
Python process to modify the filesystem outside its working directory —
including writes, overwrites, and deletions.

## What it checks

Three categories of attack are attempted, each targeting a sentinel file
created at `/tmp/pybox-sentinel.txt` *before* the sandbox runs:

| Attack | Syscall | Expected result |
|--------|---------|-----------------|
| Write a new file outside CWD | `open()` / `write()` | `PermissionError` |
| Overwrite an existing file outside CWD | `open()` / `write()` | `PermissionError` |
| Delete a file outside CWD | `unlink()` | `PermissionError` |

Write and delete are separate syscalls (`open`/`write` vs `unlink`). Both are
blocked independently by the kernel-level sandbox.

## Setup

Uses a `pip`-based venv.

```
python -m venv .venv
pip install pybox
```

## File layout

```
04-filesystem-attacks/
├── README.md
├── Makefile
└── attack.py    # Runs all three attack scenarios and reports results
```

## Make targets

| Target | Description |
|--------|-------------|
| `make setup` | Create venv, install pybox |
| `make attack` | Create sentinels, run all attacks, verify sentinels are intact |
| `make clean` | Remove venv |

## Expected output

All three attacks raise `PermissionError`. The sentinel files are intact after
the run. `make attack` exits non-zero if any attack unexpectedly succeeds.
