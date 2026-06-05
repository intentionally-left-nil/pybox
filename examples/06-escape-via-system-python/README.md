# Example: Escape via System Python

This example demonstrates that a sandboxed Python process cannot escape the
sandbox by spawning `/usr/bin/python3` or another interpreter directly.

## The attack idea

A naive mental model of pybox is: "the wrapper script invokes nono, which
sandboxes *that* Python process." An attacker might reason: "if I exec the
system Python directly — bypassing the wrapper entirely — I get a fresh,
unsandboxed process."

This does not work.

## Why it does not work

nono's sandbox (Apple Seatbelt on macOS, Landlock on Linux) is applied to the
**entire process tree** rooted at the supervised command, not just the initial
process. When `nono run ... -- python script.py` executes, the Seatbelt policy
covers every child process that `python` spawns — including `os.system()`,
`subprocess.run()`, `exec()`, and `fork()` calls. The child inherits the
sandbox. There is no way for a child process to escalate its own privileges.

## Attack vectors attempted

| Attack | Method |
|--------|--------|
| `os.system` | `os.system("/usr/bin/python3 -c 'open(..., w)'")` |
| `subprocess.run` | `subprocess.run(["/usr/bin/python3", "-c", "..."])` |
| `subprocess` via shell | `subprocess.run("bash -c '...'", shell=True)` |
| `os.execv` replacement | `os.execv("/usr/bin/python3", [...])` — replaces the current process |

The `os.execv` case is interesting: it *replaces* the current Python process
with the system Python. But the replacement process is still a child of the
nono supervisor and still runs under the same Seatbelt policy.

## Setup

Uses a `uv`-based venv.

```
uv venv .venv
uv pip install pybox
```

## File layout

```
06-escape-via-system-python/
├── README.md
├── Makefile
└── escape.py    # Attempts all escape vectors, reports results
```

## Make targets

| Target | Description |
|--------|-------------|
| `make setup` | Create venv, install pybox |
| `make escape` | Create sentinel, run all escape attempts, verify sentinel intact |
| `make clean` | Remove venv |

## Expected output

All escape attempts fail. The sentinel file at `/tmp/pybox-escape-sentinel.txt`
is untouched after the run.
