# pybox Launcher Design

This document describes the pybox wrapper/launcher architecture: the original
shell-script design, the problems it encountered when running inside a venv, and
the rewrite to a native Go binary.

---

## v1: Shell Script Wrappers

### How it worked

When `pip install pybox` ran inside a venv, the `.pth` hook fired on the first
Python startup and called `_install.run()`. That function:

1. Scanned `bin/` for all `python*` and `pip*` symlinks pointing to the real
   interpreter.
2. Wrote two shell scripts — `pybox_wrapper.sh` and `pybox_pip_wrapper.sh` —
   each containing hardcoded absolute paths to the venv, the nono profile JSON,
   and the real interpreter.
3. Renamed all `python*` / `pip*` symlinks to point at the appropriate wrapper
   script.
4. Created `python_nosandbox` (symlink → real CPython binary) and `pip_nosandbox`
   (either a symlink or a rewritten console script) so the wrappers had a
   non-sandboxed target to exec into.

The wrapper scripts looked like:

```sh
#!/bin/sh
# check nono is on PATH ...
mkdir -p "/abs/path/to/venv/__pycache__"
PYTHONPYCACHEPREFIX="..." \
VIRTUAL_ENV="..." \
  exec nono run --allow-cwd \
    --profile "/abs/path/to/venv/share/pybox/pybox_profile.json" \
    -- "/abs/path/to/venv/bin/python_nosandbox" "$@"
```

### Why nosandbox stashes live in bin/ (not a subdirectory)

CPython discovers its virtual environment by looking for `pyvenv.cfg` one
directory above `sys.executable` (using the *unresolved* `argv[0]` path, not the
resolved binary path). This means the stash files must live directly in `bin/`,
not in a subdirectory like `bin/nosandbox/`.

If `python_nosandbox` lived at `bin/nosandbox/python`, then `argv[0]` would be
`bin/nosandbox/python` and CPython would look for `pyvenv.cfg` at `bin/` — not
found. With the stash directly in `bin/`, `argv[0]` is `bin/python_nosandbox` and
CPython looks one level up at `venv/` — where `pyvenv.cfg` actually lives. The
venv activates correctly.

### The double-shebang problem

The shell script design worked for direct invocations (`python script.py`,
`python -m module`) but broke any code path that used `os.execvp()` to launch a
console script directly.

The specific failure: `jupyter_core.command` dispatches subcommands by calling
`os.execvp("jupyter-nbconvert", ...)`. The kernel resolves:

```
execvp("jupyter-nbconvert")
  → shebang: #!/.venv/bin/python3.14
    → python3.14 is a symlink → pybox_wrapper.sh  (#!/bin/sh)
      → ENOEXEC: kernel does not follow two levels of #!
```

The Linux/macOS kernel supports exactly one level of `#!` indirection. When
`execve()` is called on a script, it reads the shebang and re-execs the named
interpreter with the script as an argument. If *that* interpreter is also a `#!`
script, the kernel returns `ENOEXEC` — it does not recurse. Because
`pybox_wrapper.sh` was a shell script, any console script whose shebang resolved
through it triggered this error.

---

## v2: Native Go Launcher

### Design

The fix is to replace the shell scripts with a real native binary. A Mach-O/ELF
binary can be the target of a `#!` shebang line without issue — the kernel runs
it directly. The double-shebang problem disappears.

The launcher (`pybox_launcher`) is a small Go program that:

1. Determines which config file to read based on `argv[0]` basename:
   - `pip*` invocations → `pybox_pip_launcher.env`
   - everything else → `pybox_launcher.env`
2. Reads the config file from the same directory as `argv[0]` (the symlink's
   directory, not the resolved binary's directory).
3. Checks `NONO_CAP_FILE` — if set, we are already inside a nono sandbox (see
   below) and exec directly into `python_nosandbox`, bypassing nono entirely.
4. Verifies `nono` is on PATH.
5. Runs `mkdir -p` on any directories listed in `PYBOX_MKDIR`.
6. Applies `PYBOX_ENV_*` entries as environment variable overrides.
7. `syscall.Exec`s into `nono run --allow-cwd --profile <profile> -- <nosandbox> <args...>`.

### Config file format

Config files are plain `KEY=VALUE` text (one per line, `#` comments). All paths
are absolute and hardcoded at install time by `_install.py`.

```
# pybox launcher config — python entry points
PYBOX_NONO_PROFILE=/abs/path/to/venv/share/pybox/pybox_profile.json
PYBOX_NOSANDBOX=/abs/path/to/venv/bin/python_nosandbox
PYBOX_MKDIR=/abs/path/to/venv/__pycache__
PYBOX_ENV_PYTHONPYCACHEPREFIX=/abs/path/to/venv/__pycache__
PYBOX_ENV_VIRTUAL_ENV=/abs/path/to/venv
```

The pip variant adds cache dir and pip-specific env vars:

```
# pybox launcher config — pip entry points
PYBOX_NONO_PROFILE=/abs/path/to/venv/share/pybox/pybox_pip_profile.json
PYBOX_NOSANDBOX=/abs/path/to/venv/bin/pip_nosandbox
PYBOX_MKDIR=/abs/path/to/venv/__pycache__:/abs/path/to/venv/pip-cache
PYBOX_ENV_PYTHONPYCACHEPREFIX=/abs/path/to/venv/__pycache__
PYBOX_ENV_VIRTUAL_ENV=/abs/path/to/venv
PYBOX_ENV_PIP_CACHE_DIR=/abs/path/to/venv/pip-cache
PYBOX_ENV_PIP_NO_INPUT=1
PYBOX_ENV_PIP_DISABLE_PIP_VERSION_CHECK=1
```

### Distribution

Four pre-compiled binaries are bundled inside the wheel under `pybox/bin/`:

| File | Platform |
|---|---|
| `pybox-launcher-darwin-arm64` | macOS Apple Silicon |
| `pybox-launcher-darwin-amd64` | macOS Intel |
| `pybox-launcher-linux-amd64`  | Linux x86_64 |
| `pybox-launcher-linux-arm64`  | Linux aarch64 |

At install time, `_install.py` selects the right binary via `platform.system()`
and `platform.machine()`, copies it into `bin/pybox_launcher`, and makes it
executable. No compiler is required on the user's machine.

### Execution flow (v2)

```
User/agent calls:  .venv/bin/python script.py
                         │
                         ▼
              bin/python  (symlink)
                         │
                         ▼
              bin/pybox_launcher  (native Mach-O/ELF binary)
                         │
                    reads pybox_launcher.env
                    checks NONO_CAP_FILE
                    mkdir -p __pycache__
                    sets PYTHONPYCACHEPREFIX, VIRTUAL_ENV
                         │
                         ▼
              nono run --allow-cwd --profile pybox_profile.json
                         │
                         ▼
              bin/python_nosandbox  (symlink → real CPython)
                         │
                         ▼
              script.py runs inside the nono sandbox
```

When a sandboxed Python process uses `os.execvp("jupyter-nbconvert", ...)`:

```
os.execvp("jupyter-nbconvert")
  → shebang: #!/.venv/bin/python3.14
    → python3.14 is a symlink → pybox_launcher  (native binary ✓)
      → pybox_launcher detects NONO_CAP_FILE is set
        → exec directly into python_nosandbox (no nested nono)
          → jupyter-nbconvert runs inside the existing sandbox
```

---

## nono-inside-nono: Reentrance Detection

### The problem

nono sets `NONO_CAP_FILE` in the environment of every process it sandboxes,
pointing to the active session's capability manifest. If a sandboxed process
invokes `python` (which calls the launcher, which calls `nono run`), a second
nono instance starts inside the first sandbox. This fails hard:

- The inner nono tries to write its audit log to `~/.nono/audit/` — blocked by
  the outer sandbox.
- The inner nono tries to read `~/.config/nono/profiles/` to load the profile —
  also blocked.
- Result: the inner nono crashes before the command runs, with 8+ path denial
  errors.

This is not a graceful passthrough; it is a hard failure. Any code that calls
`python` from inside a sandboxed Python process (e.g. a subprocess, a test
runner, a build tool) would fail.

### The fix

The launcher checks `NONO_CAP_FILE` before doing anything with nono:

```go
if os.Getenv("NONO_CAP_FILE") != "" {
    // Already inside a nono sandbox. Exec directly into the nosandbox
    // binary — the outer sandbox policy already constrains us.
    syscall.Exec(nosandbox, append([]string{nosandbox}, os.Args[1:]...), os.Environ())
}
```

When already sandboxed, the launcher execs directly into `python_nosandbox`,
bypassing the `nono run` wrapper entirely. The outer sandbox's policy remains in
effect — no capabilities are gained. The full inherited environment is preserved
(the outer sandbox's `allow_vars` already filtered it; filtering again would
strip vars like `VIRTUAL_ENV` that the outer sandbox explicitly passed through).

---

## Bug Fixes Made During This Work

### `pip_nosandbox` self-symlink

**Root cause**: `_install.py` used `pip_bin.is_symlink()` to decide how to create
`pip_nosandbox` at the *end* of `run()`, after the rewiring loop had already
turned `pip` into a symlink to `pybox_launcher`. In Case 2 (console-script pip),
`real_pip` was set to `pip_nosandbox` as a presence marker, and then the Case 1
branch fired (because `pip` was now a symlink) and created the circular symlink
`pip_nosandbox → pip_nosandbox`.

**Fix**: Capture `pip_was_symlink = pip_bin.is_symlink()` and the pip script
content *before* any rewiring, and use that saved state at stash time.

### `~/.CFUserTextEncoding` blocked on macOS

CoreFoundation reads `~/.CFUserTextEncoding` at startup to determine the user's
text encoding. This file is blocked by nono's default profile. Added it to
`filesystem.read` in the python profile.

### `--silent` flag removed

The original shell wrappers passed `--silent` to `nono run`, suppressing all nono
diagnostic output. This made debugging impossible. Removed in the process of
investigating the `Exec format error`.

### Makefile sentinel updated

The example Makefile used `$(VENV)/bin/pybox_wrapper.sh` as the sentinel file for
the setup target. Updated to `$(VENV)/bin/pybox_launcher` to match the new
binary-based install.
