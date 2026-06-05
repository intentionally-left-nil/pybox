"""
pybox .pth hook — runs on every Python startup in the venv.

Three cases:
1. pybox_launcher doesn't exist AND we're not inside pip → first run, trigger install
2. pybox_launcher exists → setup is complete, no-op
3. pybox_launcher doesn't exist AND we are inside pip → skip install

Case 3 prevents a race condition where pybox is being installed via pip for the
first time.  The sequence that causes it:

  a. User runs: python -m pip install .   (python is still the real interpreter)
  b. Python starts, .pth hook fires: pybox_launcher doesn't exist → _install.run()
  c. _install.run() rewires python* and pip* symlinks to pybox_launcher
  d. pip's main() continues running; sys.executable is still python3.14 in memory,
     but the symlink on disk now points to pybox_launcher.
  e. pip creates a build-isolation env in the system temp dir (TMPDIR not yet
     redirected, since the launcher never ran for THIS process).
  f. pip spawns: sys.executable pip-runner.py install ... --prefix <system-tmp>
  g. The OS resolves sys.executable → pybox_launcher (rewired in step c).
  h. pybox_launcher applies the nono sandbox, which denies writes to system tmp.
  i. The build-dep install fails with "Operation not permitted".

By skipping install when we detect we're inside pip, we defer the rewiring until
the next Python startup that is NOT pip — e.g. the first time the user runs
`python` directly or `python -c ...`.  At that point there is no mid-flight pip
process and the rewiring is safe.

Detection: pip subprocesses have argv[0] matching pip's internal scripts
(__pip-runner__.py, _in_process.py) or the top-level pip invocation uses -m with
argv starting with '-m'.  We also check for PIP_BUILD_TRACKER (set by pip during
build operations).  Either signal is sufficient to skip install.

After install, this hook re-execs the current process through nono so that the
very first `python` invocation is sandboxed.  Without this re-exec, the process
that triggered the install would run user code as the real interpreter (no nono
involved), because the launcher binary was not in the exec chain for this process.

Re-exec sequence (only on first install):
  1. _install.run() writes pybox_launcher, pybox_launcher.env, python_nosandbox,
     and the nono profile.
  2. This hook reads pybox_launcher.env to find PYBOX_NONO_PROFILE and
     PYBOX_NOSANDBOX, applies PYBOX_ENV_* overrides to the environment, and
     pre-creates PYBOX_MKDIR directories.
  3. os.execvp replaces the current process with:
       nono run --allow-cwd --profile <profile> -- python_nosandbox <original-argv>
     The kernel loads nono, which then execs python_nosandbox under the sandbox.
  4. If nono is not on PATH the re-exec is skipped and a warning is printed.

No bypass detection is needed for nosandbox: bin/python_nosandbox is a symlink to
the base CPython binary.  Because it lives directly in bin/, CPython does find
pyvenv.cfg one level up and activates the venv — but the .pth hook only fires
when site-packages are loaded, and at that point pybox_launcher already exists,
so this hook is a no-op for the nosandbox path.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def _inside_pip() -> bool:
    """
    Return True if this Python process was spawned by pip (or IS pip).

    We check two independent signals:

    1. argv[0]: pip subprocesses use paths ending in __pip-runner__.py or
       _in_process.py (pyproject-hooks).  The top-level `python -m pip`
       invocation has argv[0] == '-m' (CPython sets this before site runs).

    2. PIP_BUILD_TRACKER env var: set by pip during build operations for the
       entire subprocess tree.  Absent for normal Python invocations.
    """
    if os.environ.get("PIP_BUILD_TRACKER"):
        return True
    argv0 = sys.argv[0] if sys.argv else ""
    # `python -m pip ...` → argv[0] is '-m'
    if argv0 == "-m":
        return True
    # pip internal subprocess scripts
    _PIP_SCRIPTS = ("__pip-runner__.py", "_in_process.py")
    if any(argv0.endswith(s) for s in _PIP_SCRIPTS):
        return True
    return False


def _parse_launcher_env(env_path: Path) -> dict[str, str]:
    """Parse a pybox_launcher.env file into a key→value dict."""
    result: dict[str, str] = {}
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, _, v = line.partition("=")
            result[k.strip()] = v.strip()
    return result


def _reexec_under_nono(bin_dir: Path) -> None:
    """
    Re-exec the current process through nono using the just-installed config.

    Reads pybox_launcher.env, pre-creates PYBOX_MKDIR directories, applies
    PYBOX_ENV_* overrides, then os.execvp into:
        nono run --allow-cwd --profile <profile> -- <python_nosandbox> <argv...>

    This replaces the current (unsandboxed) process image with a sandboxed one.
    If nono is not on PATH or the config file is missing, logs a warning and
    returns without re-execing (best-effort; user will be unsandboxed this run).
    """
    env_file = bin_dir / "pybox_launcher.env"
    if not env_file.is_file():
        print(
            "pybox: warning: pybox_launcher.env not found after install; "
            "skipping re-exec (this invocation is unsandboxed).",
            file=sys.stderr,
        )
        return

    nono = shutil.which("nono")
    if nono is None:
        # nono not available — sandbox won't work anyway; install warned already.
        return

    config = _parse_launcher_env(env_file)
    profile = config.get("PYBOX_NONO_PROFILE", "")
    nosandbox = config.get("PYBOX_NOSANDBOX", "")
    if not profile or not nosandbox:
        print(
            "pybox: warning: incomplete pybox_launcher.env after install; "
            "skipping re-exec (this invocation is unsandboxed).",
            file=sys.stderr,
        )
        return

    # Pre-create PYBOX_MKDIR directories (same as the launcher binary does).
    mkdir_val = config.get("PYBOX_MKDIR", "")
    if mkdir_val:
        for d in mkdir_val.split(":"):
            if d:
                Path(d).mkdir(parents=True, exist_ok=True)

    # Apply PYBOX_ENV_* overrides to the environment.
    env = os.environ.copy()
    for k, v in config.items():
        if k.startswith("PYBOX_ENV_"):
            env_key = k[len("PYBOX_ENV_"):]
            env[env_key] = v

    # Build the nono command — same as the launcher binary would construct.
    #
    # sys.argv during site.py startup:
    #   interactive python          → ['']    (empty string sentinel)
    #   python script.py arg...    → ['script.py', 'arg', ...]
    #   python -c "code" arg...    → ['-c', 'arg', ...]  (code not recoverable)
    #   python -m mod ...          → ['-m', ...]  (blocked by _inside_pip, never reaches here)
    #
    # The Go launcher passes os.Args[1:] — everything after the python symlink
    # name.  The equivalent here is sys.argv itself (not sys.argv[1:], because
    # sys.argv[0] IS the first user-visible argument, not the interpreter name).
    #
    # Special case: interactive invocation has sys.argv == [''], where '' is a
    # CPython sentinel meaning "no script".  Passing '' to nosandbox would make
    # Python treat it as a path and try to run __main__ from cwd.  Pass nothing
    # instead so nosandbox drops into an interactive REPL.
    #
    # Special case: -c invocations — the code string is not in sys.argv and
    # cannot be reconstructed.  We skip re-exec for -c so the hook returns
    # normally; the process is unsandboxed for this one invocation only.
    user_argv = sys.argv if sys.argv else []
    if user_argv == [""]:
        # Interactive REPL: pass no args to nosandbox.
        user_argv = []
    elif user_argv[:1] == ["-c"]:
        # Can't reconstruct the -c code string; skip re-exec.
        return

    cmd = [nono, "run"]
    if os.environ.get("PYBOX_INTERACTIVE") != "1":
        cmd.append("--silent")
    cmd += ["--allow-cwd", "--profile", profile, "--", nosandbox] + user_argv

    os.execvpe(nono, cmd, env)
    # os.execvpe never returns on success.


def _check() -> None:
    bin_dir = Path(sys.executable).parent
    if not (bin_dir / "pybox_launcher").is_file():
        if _inside_pip():
            return
        from pybox import _install
        _install.run()
        # Re-exec through nono so this first invocation is sandboxed.
        _reexec_under_nono(bin_dir)


_check()
