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

No bypass detection is needed for nosandbox: bin/python_nosandbox is a symlink to
the base CPython binary.  Because it lives directly in bin/, CPython does find
pyvenv.cfg one level up and activates the venv — but the .pth hook only fires
when site-packages are loaded, and at that point pybox_launcher already exists,
so this hook is a no-op for the nosandbox path.
"""

from __future__ import annotations

import os
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


def _check() -> None:
    bin_dir = Path(sys.executable).parent
    if not (bin_dir / "pybox_launcher").is_file():
        if _inside_pip():
            return
        from pybox import _install
        _install.run()


_check()
