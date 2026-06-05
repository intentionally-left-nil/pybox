# pybox

pybox is a security sandbox for Python environments used by AI agents and untrusted automation. Install it into any virtual environment and it replaces the `python` and `pip` executables with hardened wrappers that enforce filesystem restrictions at the kernel level — no changes to your agent code required.

## How it works

Once installed, pybox intercepts every `python` and `pip` invocation in the environment and runs them under [nono](https://nono.sh), a syscall-level sandbox (Apple Seatbelt on macOS, Landlock on Linux). The restrictions are:

- **Writes** are limited to the current working directory.
- **Reads** are scoped to the virtual environment itself.
- **pip installs** cannot touch global `site-packages` or `__pycache__`.
- **Credentials** (`~/.ssh`, `~/.aws`, `~/.gcloud`, etc.) are blocked from reads.
- **Subprocess escapes** are covered — the sandbox applies to the entire process tree, not just the top-level Python process.

The wrappers are transparent to callers. Existing scripts and tools invoke `python` or `pip` as usual and receive sandboxed execution automatically.

## Requirements

- Python 3.14+
- [nono](https://nono.sh) must be installed and on `PATH`
- macOS (arm64 or amd64) or Linux (amd64 or arm64)

## Installation

pybox is not yet published to PyPI. Install directly from this repository:

```sh
pip install git+https://github.com/intentionally-left-nil/pybox.git
```

Or clone and install locally:

```sh
git clone https://github.com/intentionally-left-nil/pybox.git
cd pybox
pip install .
```

The install is a one-time operation per virtual environment. On the first Python startup after installation, pybox automatically configures itself: it rewires the `python*` and `pip*` symlinks in the environment's `bin/` directory and writes the nono sandbox profiles. No manual setup step is needed.

## Usage

Activate your virtual environment and use it normally:

```sh
source .venv/bin/activate
python my_script.py      # runs inside the sandbox
pip install requests     # installs into the venv, writes blocked outside it
```

For AI agents, prepend the venv's `bin/` to `PATH` before invoking the agent:

```sh
PATH=".venv/bin:$PATH" your-agent run ...
```

The agent's Python calls will be sandboxed without any changes to the agent itself.

## What is blocked

| Attempt | Result |
|---|---|
| Write to `/tmp` or any path outside CWD | `PermissionError` |
| Read `~/.ssh`, `~/.aws`, `~/.docker`, `~/.config/gcloud` | `PermissionError` |
| Access injected env vars (`SECRET_API_KEY`, `DATABASE_PASSWORD`, etc.) | Stripped at sandbox boundary |
| `os.system('/usr/bin/python3 ...')` subprocess escape | Blocked (entire process tree is sandboxed) |
| Malicious pip package overwriting venv binaries at install time | Blocked |
| `.pth` injection into `site-packages` | Blocked |

## Caveats

**nono must be installed separately.** pybox does not bundle nono. Install it from [nono.sh](https://nono.sh) before using pybox.

**Python 3.14 or later is required.** The `.pth`-based auto-install mechanism relies on behavior stabilized in 3.14.

**The sandbox activates on the first Python startup.** If you run `python` immediately after `pip install pybox` in the same process, the sandbox is not yet wired. Start a new Python process (or a new shell) after installation.

**Write access is CWD-scoped, not project-scoped.** The sandbox allows writes to whatever directory Python is invoked from. If you invoke Python from `/`, the restriction is effectively useless. Invoke Python from your project directory.

**nono is not available on Windows.** pybox only supports macOS and Linux.

**Nested sandboxes are handled automatically.** If `NONO_CAP_FILE` is set (i.e., you are already inside a nono sandbox), pybox skips the outer `nono run` call and execs the interpreter directly to avoid double-sandboxing failures.

## Examples

The `examples/` directory contains runnable demonstrations:

- `01-jupyter-notebook` — Jupyter session works normally; writes outside CWD are blocked
- `02-fastapi-server` — FastAPI server runs; `/escape` endpoint is blocked at the OS level
- `03-ai-agent` — opencode agent with sandboxed Python; exfiltration attempts fail
- `04-filesystem-attacks` — four write-attack vectors, all blocked
- `05-secrets-protection` — credential reads and env var exfiltration blocked
- `06-escape-via-system-python` — subprocess escape attempts via system Python blocked
- `07-pip-cannot-corrupt-sandbox` — malicious build hook cannot overwrite venv binaries
- `08-readonly-venv` — venv integrity preserved; `.pth` injection and package overwrites blocked

Each example has a `Makefile` with `setup`, `run` (or `attack`), and `clean` targets.

## License

See [LICENSE](LICENSE).
