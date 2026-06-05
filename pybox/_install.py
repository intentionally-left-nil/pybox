"""
pybox install hook.

Runs on first Python startup in the venv (triggered by pybox.pth via _pth_hook.py).
Rewires all python* and pip* symlinks in the venv's bin/ directory to go through
pybox wrapper scripts, stashing the real binaries in bin/nosandbox/.
"""

from __future__ import annotations

import os
import stat
import sys
import tempfile
from pathlib import Path


def _find_symlinks_for(bin_dir: Path, real_path: Path) -> list[Path]:
    """Return all symlinks in bin_dir whose resolved target equals real_path."""
    results = []
    for entry in bin_dir.iterdir():
        if entry.is_symlink():
            try:
                if entry.resolve() == real_path:
                    results.append(entry)
            except OSError:
                pass
    return results


def _write_wrapper(path: Path, nosandbox_target: Path) -> None:
    """Write a #!/bin/sh wrapper script to path (not yet chmod'd or renamed)."""
    content = f"#!/bin/sh\nexec {nosandbox_target} \"$@\"\n"
    path.write_text(content)
    # chmod +x
    current = stat.S_IMODE(path.stat().st_mode)
    path.chmod(current | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def run() -> None:
    bin_dir = Path(sys.executable).parent
    real_python = Path(sys.executable).resolve()

    nosandbox_dir = bin_dir / "nosandbox"
    nosandbox_python = nosandbox_dir / "python"
    wrapper_script = bin_dir / "pybox_wrapper.sh"

    print(f"pybox: setting up sandbox wrappers in {bin_dir}", file=sys.stderr)

    # --- nosandbox directory ---
    nosandbox_dir.mkdir(exist_ok=True)

    # --- nosandbox/python symlink ---
    if nosandbox_python.exists() or nosandbox_python.is_symlink():
        nosandbox_python.unlink()
    nosandbox_python.symlink_to(real_python)

    # --- pybox_wrapper.sh (write to temp, rename atomically last) ---
    tmp_wrapper = bin_dir / "pybox_wrapper.sh.tmp"
    _write_wrapper(tmp_wrapper, nosandbox_python)

    # --- pip (optional) ---
    pip_wrapper_script = bin_dir / "pybox_pip_wrapper.sh"
    pip_symlinks: list[Path] = []
    real_pip: Path | None = None

    pip_bin = bin_dir / "pip"
    if pip_bin.is_symlink():
        real_pip = pip_bin.resolve()
        nosandbox_pip = nosandbox_dir / "pip"
        if nosandbox_pip.exists() or nosandbox_pip.is_symlink():
            nosandbox_pip.unlink()
        nosandbox_pip.symlink_to(real_pip)

        tmp_pip_wrapper = bin_dir / "pybox_pip_wrapper.sh.tmp"
        _write_wrapper(tmp_pip_wrapper, nosandbox_pip)

        pip_symlinks = _find_symlinks_for(bin_dir, real_pip)

    # --- rewire python symlinks → pybox_wrapper.sh ---
    python_symlinks = _find_symlinks_for(bin_dir, real_python)
    for link in python_symlinks:
        link.unlink()
        link.symlink_to(wrapper_script)

    # --- rewire pip symlinks → pybox_pip_wrapper.sh ---
    for link in pip_symlinks:
        link.unlink()
        link.symlink_to(pip_wrapper_script)

    # --- atomic commit: rename pip wrapper first, python wrapper last ---
    if real_pip is not None:
        os.rename(bin_dir / "pybox_pip_wrapper.sh.tmp", pip_wrapper_script)

    os.rename(tmp_wrapper, wrapper_script)  # sentinel — must be last

    print("pybox: sandbox wrappers installed successfully.", file=sys.stderr)
