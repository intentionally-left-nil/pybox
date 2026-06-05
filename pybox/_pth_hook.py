"""
pybox .pth hook — runs on every Python startup in the venv.

Two cases:
1. pybox_wrapper.sh doesn't exist → first run, trigger install
2. pybox_wrapper.sh exists → setup is complete, no-op

No bypass detection is needed: bin/python_nosandbox is a symlink to the base
CPython binary. Because it lives directly in bin/, CPython does find pyvenv.cfg
one level up and activates the venv — but the .pth hook only fires when
site-packages are loaded, and at that point pybox_wrapper.sh already exists,
so this hook is a no-op for the nosandbox path.
"""

from __future__ import annotations

import sys
from pathlib import Path


def _check() -> None:
    bin_dir = Path(sys.executable).parent
    if not (bin_dir / "pybox_launcher").is_file():
        from pybox import _install
        _install.run()


_check()
