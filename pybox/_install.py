"""
pybox install hook.

Runs on first Python startup in the venv (triggered by pybox.pth via _pth_hook.py).
Rewires all python* and pip* symlinks in the venv's bin/ directory to go through
pybox wrapper scripts, stashing the real binaries in bin/nosandbox/.

Also generates nono sandbox profiles under <venv>/share/pybox/:
  pybox_profile.json      — for the python* wrappers
  pybox_pip_profile.json  — for the pip* wrappers

Profiles are hardcoded to the absolute venv path so they remain correct
regardless of the user's working directory at invocation time.
"""

from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

_PYBOX_VERSION = "0.1.0"


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


def _find_pip_scripts(bin_dir: Path, real_python: Path) -> list[Path]:
    """
    Return all pip* executables in bin_dir that belong to this venv.

    Handles two layouts:
    - Symlink → a real pip binary (conda / pyenv style).
    - Plain file with a shebang pointing to this venv's python (the layout
      produced by 'pip install pip', 'uv venv --seed', and python -m venv).

    Only the plain-file case is returned here; symlinks are handled by the
    existing _find_symlinks_for path keyed on real_pip.
    """
    venv_python_paths = {str(real_python), str(bin_dir / "python")}
    results = []
    for entry in bin_dir.iterdir():
        if not entry.name.startswith("pip"):
            continue
        if entry.is_symlink():
            continue  # handled via _find_symlinks_for against real_pip
        if not entry.is_file():
            continue
        # Read the shebang line (first line, up to 512 bytes).
        try:
            with entry.open("rb") as fh:
                first = fh.readline(512).decode("utf-8", errors="replace").strip()
        except OSError:
            continue
        if not first.startswith("#!"):
            continue
        shebang_target = first[2:].split()[0]  # strip args like -E
        if shebang_target in venv_python_paths or Path(shebang_target).resolve() == real_python:
            results.append(entry)
    return results


def _write_wrapper(path: Path, nosandbox_target: Path) -> None:
    """Write a #!/bin/sh wrapper script to path (not yet chmod'd or renamed)."""
    content = f"#!/bin/sh\nexec {nosandbox_target} \"$@\"\n"
    path.write_text(content)
    # chmod +x
    current = stat.S_IMODE(path.stat().st_mode)
    path.chmod(current | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _validate_venv_path(venv_root: Path) -> None:
    """
    Raise ValueError if the venv path cannot be safely embedded in JSON or a
    shell script.  Covers double-quote and backslash (which would break the
    shell wrapper) and non-printable bytes (which would silently corrupt JSON).
    Spaces and other special chars are fine inside JSON strings.
    """
    s = str(venv_root)
    for ch in s:
        if ch == '"' or ch == '\\' or not ch.isprintable():
            raise ValueError(
                f"pybox: venv path contains an unsafe character ({ch!r}) "
                f"that cannot be embedded in a shell script or JSON profile: {s}"
            )


def _python_exe_names(bin_dir: Path, real_python: Path) -> list[str]:
    """
    Return the names (not full paths) of all python* entries in bin_dir that
    are either the real interpreter or a symlink resolving to it.  These are
    the names the pip profile must individually deny to prevent overwriting.
    """
    names = set()
    for entry in bin_dir.iterdir():
        name = entry.name
        if not name.startswith("python"):
            continue
        # Real interpreter itself
        if entry.resolve() == real_python:
            names.add(name)
            continue
        # Plain files named python* (e.g. python3.14 in some layouts)
        if entry.is_file() and not entry.is_symlink():
            names.add(name)
    return sorted(names)


def _build_python_profile(venv_root: Path) -> dict:
    """
    Build the nono profile dict for the python* wrappers.

    Policy:
    - Extends 'default' for system paths and credential denies.
    - Excludes dangerous_commands* (deprecated startup-only blocks; would prevent
      the agent running rm/chmod in its workspace) and user_tools (~/.local/bin
      write access that agents shouldn't have).
    - workdir: readwrite — the agent can freely edit its working directory.
    - venv: read-only for imports/libraries, write only to __pycache__.
    - deny venv/bin entirely — even when the venv is inside the workdir the deny
      wins over the parent readwrite grant (verified experimentally on macOS
      Seatbelt; Linux Landlock to be tested when wrappers invoke nono).
    - bypass_protection on the venv root — required when the venv is named '.env'
      because deny_shell_configs would otherwise block the entire tree. Safe to
      include unconditionally; it is a no-op for any other venv name.
    """
    venv_str = str(venv_root)
    return {
        "meta": {
            "name": "pybox",
            "version": _PYBOX_VERSION,
            "description": (
                "pybox python sandbox: read venv, write only to venv/__pycache__, "
                "read+write $WORKDIR, deny all writes to venv/bin"
            ),
        },
        "extends": "default",
        "groups": {
            "exclude": [
                "dangerous_commands",
                "dangerous_commands_macos",
                "dangerous_commands_linux",
                "user_tools",
            ]
        },
        "workdir": {"access": "readwrite"},
        "filesystem": {
            "read": [venv_str],
            "write": [f"{venv_str}/__pycache__"],
            "deny": [f"{venv_str}/bin"],
            "bypass_protection": [venv_str],
        },
    }


def _build_pip_profile(venv_root: Path, python_exe_names: list[str]) -> dict:
    """
    Build the nono profile dict for the pip* wrappers.

    Policy differences from the python profile:
    - workdir: read only — pip has no reason to write into the project tree.
    - venv/bin is writable so pip can install console-script entrypoints.
    - Individual python executables, pybox wrappers, and nosandbox/ are
      explicitly denied so pip cannot overwrite the interpreter or wrappers
      even though the rest of bin/ is writable.
    - lib, lib64, include, share, __pycache__, pip-cache are all writable
      for normal package installation.
    """
    venv_str = str(venv_root)

    # Files in bin/ that must never be overwritten by pip.
    protected_bin = (
        [f"{venv_str}/bin/{name}" for name in python_exe_names]
        + [
            f"{venv_str}/bin/pybox_wrapper.sh",
            f"{venv_str}/bin/pybox_pip_wrapper.sh",
            f"{venv_str}/bin/nosandbox",
        ]
    )

    return {
        "meta": {
            "name": "pybox-pip",
            "version": _PYBOX_VERSION,
            "description": (
                "pybox pip sandbox: read $WORKDIR, write to venv for installs, "
                "deny writes to venv/bin python executables and pybox wrappers"
            ),
        },
        "extends": "default",
        "groups": {
            "exclude": [
                "dangerous_commands",
                "dangerous_commands_macos",
                "dangerous_commands_linux",
                "user_tools",
            ]
        },
        "workdir": {"access": "read"},
        "filesystem": {
            "read": [venv_str],
            "write": [
                f"{venv_str}/lib",
                f"{venv_str}/lib64",
                f"{venv_str}/include",
                f"{venv_str}/share",
                f"{venv_str}/__pycache__",
                f"{venv_str}/pip-cache",
                f"{venv_str}/bin",
            ],
            "deny": protected_bin,
            "bypass_protection": [venv_str],
        },
    }


def _write_profile(profile_dir: Path, filename: str, profile: dict) -> None:
    """Atomically write a profile JSON file under profile_dir."""
    dest = profile_dir / filename
    tmp = profile_dir / f"{filename}.tmp"
    tmp.write_text(json.dumps(profile, indent=2) + "\n")
    os.rename(tmp, dest)


def run() -> None:
    bin_dir = Path(sys.executable).parent
    real_python = Path(sys.executable).resolve()
    venv_root = bin_dir.parent.resolve()

    nosandbox_dir = bin_dir / "nosandbox"
    nosandbox_python = nosandbox_dir / "python"
    wrapper_script = bin_dir / "pybox_wrapper.sh"

    print(f"pybox: setting up sandbox in {venv_root}", file=sys.stderr)

    # Safety check: venv path must be embeddable in JSON and shell scripts.
    _validate_venv_path(venv_root)

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
    # Two cases:
    # 1. pip is a symlink to a real pip binary (conda / pyenv style).
    #    Stash the binary in nosandbox/pip, write a wrapper shim.
    # 2. pip is a console-script (plain file, shebang = this venv's python).
    #    Move each pip* script to nosandbox/, rewrite its shebang to
    #    nosandbox/python so it still works after python is rewired, then
    #    replace the original with a wrapper shim.
    pip_wrapper_script = bin_dir / "pybox_pip_wrapper.sh"
    pip_symlinks: list[Path] = []
    real_pip: Path | None = None
    pip_scripts: list[Path] = []  # console-script pip* files

    pip_bin = bin_dir / "pip"
    if pip_bin.is_symlink():
        # Case 1: symlink to a standalone pip binary
        real_pip = pip_bin.resolve()
        nosandbox_pip = nosandbox_dir / "pip"
        if nosandbox_pip.exists() or nosandbox_pip.is_symlink():
            nosandbox_pip.unlink()
        nosandbox_pip.symlink_to(real_pip)

        tmp_pip_wrapper = bin_dir / "pybox_pip_wrapper.sh.tmp"
        _write_wrapper(tmp_pip_wrapper, nosandbox_pip)

        pip_symlinks = _find_symlinks_for(bin_dir, real_pip)
    else:
        # Case 2: console-script pip* files (shebang → this venv's python)
        pip_scripts = _find_pip_scripts(bin_dir, real_python)
        if pip_scripts:
            nosandbox_pip = nosandbox_dir / "pip"
            # Move the canonical 'pip' script to nosandbox/pip, rewriting its
            # shebang to nosandbox/python so it still runs after python is rewired.
            canonical = bin_dir / "pip"
            if canonical in pip_scripts:
                source = canonical
            else:
                source = sorted(pip_scripts)[0]  # pick the first alphabetically

            # Read, fix shebang, write to nosandbox/pip
            content = source.read_bytes()
            # Replace the first line shebang with nosandbox/python
            newline_pos = content.index(b"\n")
            new_content = (
                f"#!{nosandbox_python}\n".encode() + content[newline_pos + 1:]
            )
            if nosandbox_pip.exists() or nosandbox_pip.is_symlink():
                nosandbox_pip.unlink()
            nosandbox_pip.write_bytes(new_content)
            current = stat.S_IMODE(nosandbox_pip.stat().st_mode)
            nosandbox_pip.chmod(current | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

            tmp_pip_wrapper = bin_dir / "pybox_pip_wrapper.sh.tmp"
            _write_wrapper(tmp_pip_wrapper, nosandbox_pip)
            # Mark real_pip so the profile and commit logic below activate.
            real_pip = nosandbox_pip

    # --- nono profiles ---
    # Written to <venv>/share/pybox/ with absolute hardcoded venv paths so
    # they are correct regardless of the user's working directory at runtime.
    profile_dir = venv_root / "share" / "pybox"
    profile_dir.mkdir(parents=True, exist_ok=True)

    python_exe_names = _python_exe_names(bin_dir, real_python)

    python_profile = _build_python_profile(venv_root)
    pip_profile = _build_pip_profile(venv_root, python_exe_names)

    # pip profile first, python profile second (mirrors the wrapper commit order).
    if real_pip is not None:
        _write_profile(profile_dir, "pybox_pip_profile.json", pip_profile)
    _write_profile(profile_dir, "pybox_profile.json", python_profile)

    print(f"pybox: nono profiles written to {profile_dir}", file=sys.stderr)

    # --- rewire python symlinks → pybox_wrapper.sh ---
    python_symlinks = _find_symlinks_for(bin_dir, real_python)
    for link in python_symlinks:
        link.unlink()
        link.symlink_to(wrapper_script)

    # --- rewire pip symlinks (case 1) → pybox_pip_wrapper.sh ---
    for link in pip_symlinks:
        link.unlink()
        link.symlink_to(pip_wrapper_script)

    # --- rewire pip console-scripts (case 2) → pybox_pip_wrapper.sh ---
    for script in pip_scripts:
        script.unlink()
        script.symlink_to(pip_wrapper_script)

    # --- atomic commit: rename pip wrapper first, python wrapper last ---
    if real_pip is not None:
        os.rename(bin_dir / "pybox_pip_wrapper.sh.tmp", pip_wrapper_script)

    os.rename(tmp_wrapper, wrapper_script)  # sentinel — must be last

    print("pybox: sandbox wrappers installed successfully.", file=sys.stderr)
