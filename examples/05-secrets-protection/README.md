# Example: Secrets Protection

This example demonstrates that the pybox sandbox prevents sandboxed Python code
from reading sensitive files or accessing secret environment variables — two of
the most common exfiltration vectors for compromised AI agents.

## What it checks

### 1. Credential files (filesystem)

The following fake credential files are created *before* the sandbox runs.
Python attempts to open and read each one. All reads are blocked:

| File | Category |
|------|----------|
| `~/.ssh/id_rsa_fake` | SSH private key |
| `~/.aws/credentials_fake` | AWS credentials |
| `~/.docker/config_fake.json` | Docker registry token |
| `~/.config/gcloud/credentials_fake.json` | GCP credentials |

These paths fall under nono's built-in `deny_credentials` group, which is
active in every profile that extends `default`. The blocks are enforced at the
kernel level — no Python instrumentation is involved.

### 2. Secret environment variables

Environment variables not in the sandbox's `allow_vars` list are stripped
before the process starts. The sandboxed process cannot see them at all.

| Variable | What it would contain |
|----------|-----------------------|
| `SECRET_API_KEY` | Simulated API key |
| `DATABASE_PASSWORD` | Simulated DB password |
| `AWS_SECRET_ACCESS_KEY` | Simulated AWS secret |

### 3. PYTHONPATH injection

`PYTHONPATH` is unconditionally blocked by nono at the OS level, regardless of
`allow_vars`. An attacker cannot use it to inject a malicious module that runs
before the sandbox is fully established.

## Setup

Uses a `pip`-based venv.

```
python -m venv .venv
pip install pybox
```

## File layout

```
05-secrets-protection/
├── README.md
├── Makefile
└── attack.py    # Attempts to read credential files and env vars
```

## Make targets

| Target | Description |
|--------|-------------|
| `make setup` | Create venv, install pybox |
| `make attack` | Create fake credentials, run all read attempts, report results |
| `make clean` | Remove venv and fake credential files |

## Expected output

Every credential file read raises `PermissionError`. Every secret env var
resolves to `None` (absent from `os.environ`). `PYTHONPATH` injection has no
effect — the variable is not visible inside the sandbox.
