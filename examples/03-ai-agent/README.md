# Example: AI Agent (opencode)

This example shows opencode running inside a pybox-sandboxed venv. The venv is
activated so that `which python` resolves to the pybox wrapper. Any Python code
opencode executes on your behalf is automatically kernel-sandboxed — no changes
to opencode itself are required.

## Caveat

Activating the venv is a convenient way to sandbox the *code opencode runs*
without any configuration. For the strongest isolation you would also want the
opencode process itself to run under nono:

```bash
nono run --profile opencode -- opencode run "..."
```

That way even opencode's own process is kernel-sandboxed. This example focuses
on the venv-activation approach because it requires nothing beyond pybox itself.

## What it checks

opencode is given two tasks in sequence:

1. **Legitimate task** — analyse `workspace/sales.csv`, compute a summary, and
   write the result to `workspace/output/summary.txt`. This succeeds: reading
   input and writing inside the working directory are both allowed.

2. **Exfiltration attempt** — opencode is prompted to also save a copy of the
   data to `/tmp/exfiltrated.csv`. This fails: the sandbox blocks the write
   with `PermissionError`, and opencode reports the error.

## Setup

Uses a `uv`-based venv. opencode must be installed on the host (it is invoked
directly from `PATH`, not from inside the venv).

```
uv venv .venv
uv pip install pybox pandas
```

## File layout

```
03-ai-agent/
├── README.md
├── Makefile
├── workspace/
│   └── sales.csv          # Input data
└── .gitignore
```

## Make targets

| Target | Description |
|--------|-------------|
| `make setup` | Create venv, install dependencies |
| `make run` | Activate venv, run opencode with the demo task |
| `make clean` | Remove venv and generated outputs |

## How it works

`make run` activates the venv (prepending `.venv/bin` to `PATH`) before
invoking `opencode run`. From that point, whenever opencode shells out to
`python`, it hits the pybox wrapper — and nono enforces the sandbox policy on
every Python subprocess.
