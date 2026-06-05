"""
pybox .pth hook — runs on every Python startup in the venv.

Two cases:
1. pybox_wrapper.sh doesn't exist → first run, trigger install
2. pybox_wrapper.sh exists → setup is complete, no-op

No bypass detection is needed: bin/nosandbox/python is a symlink to the base
CPython binary, which resolves outside the venv directory tree and therefore
never reads pyvenv.cfg. Python won't load the venv's site-packages (and thus
won't run this .pth hook) when invoked that way, with or without bin/activate.
If this hook is firing, we're already running through the venv's Python, which
after setup is pybox_wrapper.sh.
"""

from __future__ import annotations

import sys
from pathlib import Path


def _check() -> None:
    bin_dir = Path(sys.executable).parent
    if not (bin_dir / "pybox_wrapper.sh").is_file():
        from pybox import _install
        _install.run()


_check()
