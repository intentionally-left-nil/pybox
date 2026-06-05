"""
pybox install hook.

Runs on first Python startup in the venv (triggered by pybox.pth via _pth_hook.py).
Rewires all python* and pip* symlinks in the venv's bin/ directory to go through
the pybox launcher binary, stashing the real binaries as bin/python_nosandbox
and bin/pip_nosandbox directly in bin/ (not a subdirectory — see run() for why).

The launcher binary (pybox_launcher) is a native Mach-O/ELF binary that reads a
config file (pybox_launcher.env or pybox_pip_launcher.env in the same bin/ dir),
sets up the required environment variables, pre-creates needed directories, and
exec's into nono.  Using a native binary avoids the double-shebang problem: when
a console script (e.g. jupyter-nbconvert) has a shebang pointing to python3.X,
and python3.X is a symlink to pybox_launcher (a real binary), the kernel can exec
it directly — no second #! to choke on.

Also generates nono sandbox profiles under <venv>/share/pybox/:
  pybox_profile.json      — for the python* launcher
  pybox_pip_profile.json  — for the pip* launcher

Profiles are hardcoded to the absolute venv path so they remain correct
regardless of the user's working directory at invocation time.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import stat
import sys
from pathlib import Path

_PYBOX_VERSION = "0.1.0"

# Map (system, machine) → bundled binary name.
# system:  "Darwin" | "Linux"
# machine: "arm64" | "aarch64" | "x86_64" | "AMD64"
_LAUNCHER_BINARIES: dict[tuple[str, str], str] = {
    ("Darwin", "arm64"):   "pybox-launcher-darwin-arm64",
    ("Darwin", "x86_64"):  "pybox-launcher-darwin-amd64",
    ("Linux",  "x86_64"):  "pybox-launcher-linux-amd64",
    ("Linux",  "aarch64"): "pybox-launcher-linux-arm64",
}


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


def _install_launcher_binary(bin_dir: Path) -> Path:
    """
    Copy the platform-appropriate pybox-launcher binary into bin_dir as
    'pybox_launcher', make it executable, and return its path.

    Raises RuntimeError if no binary is bundled for the current platform.
    """
    system = platform.system()    # "Darwin" | "Linux"
    machine = platform.machine()  # "arm64" | "aarch64" | "x86_64"

    binary_name = _LAUNCHER_BINARIES.get((system, machine))
    if binary_name is None:
        raise RuntimeError(
            f"pybox: no bundled launcher binary for {system}/{machine}.\n"
            f"Supported platforms: {', '.join(f'{s}/{m}' for s, m in _LAUNCHER_BINARIES)}"
        )

    # The bundled binaries live in pybox/bin/ inside the installed package.
    package_dir = Path(__file__).parent
    src = package_dir / "bin" / binary_name
    if not src.exists():
        raise RuntimeError(
            f"pybox: bundled binary not found: {src}\n"
            "The pybox package may be incomplete."
        )

    dest = bin_dir / "pybox_launcher"
    # Write to a temp file then rename atomically.
    tmp = bin_dir / "pybox_launcher.tmp"
    shutil.copy2(src, tmp)
    tmp.chmod(tmp.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    os.rename(tmp, dest)
    return dest


def _write_python_launcher_env(
    bin_dir: Path, venv_root: Path, nosandbox_python: Path
) -> None:
    """
    Write the launcher config file for the python* entry points.

    pybox_launcher reads this file (found as <bin_dir>/pybox_launcher.env)
    to learn which nono profile and nosandbox binary to use, which directories
    to pre-create, and which environment variables to set before exec'ing nono.

    Config keys:
      PYBOX_NONO_PROFILE  — absolute path to the nono profile JSON
      PYBOX_NOSANDBOX     — absolute path to the real interpreter (python_nosandbox)
      PYBOX_MKDIR         — colon-separated dirs to mkdir -p before exec
      PYBOX_ENV_*         — environment variables to set in the child process;
                            PYBOX_ENV_FOO=bar sets FOO=bar

    Note on PYTHONPATH: nono's built-in environment deny-list unconditionally
    blocks PYTHONPATH (along with LD_PRELOAD, DYLD_INSERT_LIBRARIES, etc.) —
    it cannot be passed through even if listed in allow_vars.  Users who rely
    on PYTHONPATH to import local libraries should install them into the venv
    with `pip install -e <path>` instead.

    Note on nono run vs nono wrap: the launcher uses nono run (supervised mode)
    rather than nono wrap (direct/exec mode).  Supervised mode keeps a lightweight
    nono parent process that handles signal forwarding correctly — important for
    pip's subprocess tree and for interactive Python sessions.

    Note on Jupyter dirs: Jupyter writes kernel connection files and other
    transient data to ~/Library/Jupyter (macOS) or ~/.local/share/jupyter
    (Linux), which are outside the sandbox's writable zone.  We redirect all
    three Jupyter XDG-style dirs into the venv's share/jupyter/ subtree, which
    is already writable.  PYBOX_MKDIR pre-creates them so Jupyter never needs
    to walk up and mkdir the parents.
    """
    venv_str = str(venv_root)
    profile = f"{venv_str}/share/pybox/pybox_profile.json"
    jupyter_base = f"{venv_str}/share/jupyter"
    mkdir_dirs = ":".join([
        f"{venv_str}/__pycache__",
        f"{jupyter_base}/runtime",
        f"{jupyter_base}/data",
        f"{jupyter_base}/config",
    ])
    content = "\n".join([
        "# pybox launcher config — python entry points",
        "# Auto-generated by pybox._install — do not edit by hand.",
        f"PYBOX_NONO_PROFILE={profile}",
        f"PYBOX_NOSANDBOX={nosandbox_python}",
        f"PYBOX_MKDIR={mkdir_dirs}",
        f"PYBOX_ENV_PYTHONPYCACHEPREFIX={venv_str}/__pycache__",
        f"PYBOX_ENV_VIRTUAL_ENV={venv_str}",
        f"PYBOX_ENV_JUPYTER_RUNTIME_DIR={jupyter_base}/runtime",
        f"PYBOX_ENV_JUPYTER_DATA_DIR={jupyter_base}/data",
        f"PYBOX_ENV_JUPYTER_CONFIG_DIR={jupyter_base}/config",
    ]) + "\n"
    dest = bin_dir / "pybox_launcher.env"
    tmp = bin_dir / "pybox_launcher.env.tmp"
    tmp.write_text(content)
    os.rename(tmp, dest)


def _write_pip_launcher_env(
    bin_dir: Path, venv_root: Path, nosandbox_pip: Path
) -> None:
    """
    Write the launcher config file for the pip* entry points.

    Uses pybox_pip_launcher.env so the python and pip configs are independent.

    In addition to the python launcher config:
    - PYBOX_MKDIR includes pip-cache so pip's HTTP/wheel cache is always
      available inside the sandbox from the first install.
    - PIP_CACHE_DIR redirects pip's cache into venv/pip-cache, keeping it
      inside the sandbox's writable zone (prevents pip from trying to write
      to ~/.cache/pip which would be blocked).
    - PIP_NO_INPUT=1 so pip never blocks waiting for interactive input.
    - PIP_DISABLE_PIP_VERSION_CHECK=1 to suppress pip's update nag, which
      writes to ~/.config/pip and would be blocked by the sandbox anyway.
    - Uses the pip-specific profile (pybox_pip_profile.json).
    """
    venv_str = str(venv_root)
    profile = f"{venv_str}/share/pybox/pybox_pip_profile.json"
    content = "\n".join([
        "# pybox launcher config — pip entry points",
        "# Auto-generated by pybox._install — do not edit by hand.",
        f"PYBOX_NONO_PROFILE={profile}",
        f"PYBOX_NOSANDBOX={nosandbox_pip}",
        f"PYBOX_MKDIR={venv_str}/__pycache__:{venv_str}/pip-cache",
        f"PYBOX_ENV_PYTHONPYCACHEPREFIX={venv_str}/__pycache__",
        f"PYBOX_ENV_VIRTUAL_ENV={venv_str}",
        f"PYBOX_ENV_PIP_CACHE_DIR={venv_str}/pip-cache",
        "PYBOX_ENV_PIP_NO_INPUT=1",
        "PYBOX_ENV_PIP_DISABLE_PIP_VERSION_CHECK=1",
    ]) + "\n"
    dest = bin_dir / "pybox_pip_launcher.env"
    tmp = bin_dir / "pybox_pip_launcher.env.tmp"
    tmp.write_text(content)
    os.rename(tmp, dest)


def _validate_venv_path(venv_root: Path) -> None:
    """
    Raise ValueError if the venv path cannot be safely embedded in JSON or a
    config file.  Covers double-quote and backslash (which would break config
    parsing) and non-printable bytes (which would silently corrupt JSON).
    Spaces and other special chars are fine.
    """
    s = str(venv_root)
    for ch in s:
        if ch == '"' or ch == '\\' or not ch.isprintable():
            raise ValueError(
                f"pybox: venv path contains an unsafe character ({ch!r}) "
                f"that cannot be embedded in a config file or JSON profile: {s}"
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


def _python_env_allow_vars() -> list[str]:
    """
    Environment variables the python* launcher passes through into the sandbox.

    When any allow_vars entry is present, nono clears the entire inherited
    environment and passes through only the listed variables.  We allow the
    minimal set needed for a functional Python session:

    - Basic shell environment (PATH, HOME, USER, locale, terminal type, tmp)
    - PYTHONPYCACHEPREFIX / VIRTUAL_ENV: set by the launcher itself; must be
      in allow_vars or nono will strip them before Python sees them.
    - PYBOX_*: reserved namespace for any pybox-level overrides.

    PYTHONPATH is intentionally absent.  nono's built-in environment deny-list
    unconditionally blocks PYTHONPATH (together with LD_PRELOAD,
    DYLD_INSERT_LIBRARIES, NODE_OPTIONS, etc.) regardless of allow_vars — it
    cannot be passed through.  Users who need to import from a local directory
    should install it into the venv with `pip install -e <path>` instead.
    """
    return [
        "PATH",
        "HOME",
        "USER",
        "LOGNAME",
        "LANG",
        "LC_ALL",
        "LC_*",
        "TERM",
        "COLORTERM",
        "TERM_PROGRAM",
        "TMPDIR",
        "TMP",
        "TEMP",
        "PYTHONPYCACHEPREFIX",
        "VIRTUAL_ENV",
        "VIRTUAL_ENV_PROMPT",
        "JUPYTER_*",
        "PYBOX_*",
        "NONO_CAP_FILE",
    ]


def _pip_env_allow_vars() -> list[str]:
    """
    Environment variables the pip* launcher passes through into the sandbox.

    Extends the python allow-list with pip-specific variables.  PIP_* covers
    PIP_CACHE_DIR, PIP_NO_INPUT, PIP_DISABLE_PIP_VERSION_CHECK (all set by the
    launcher itself) plus any user-configured PIP_INDEX_URL, PIP_EXTRA_INDEX_URL,
    PIP_TRUSTED_HOST, etc.
    """
    return _python_env_allow_vars() + ["PIP_*"]


def _build_python_profile(venv_root: Path, python_exe_names: list[str]) -> dict:
    """
    Build the nono profile dict for the python* launcher.

    Policy:
    - Extends 'default' for system paths and credential denies.
    - Excludes dangerous_commands* (deprecated startup-only blocks; would prevent
      the agent running rm/chmod in its workspace) and user_tools (~/.local/bin
      write access that agents shouldn't have).
    - workdir: readwrite — the agent can freely edit its working directory.
    - venv: read-only for imports/libraries, write only to __pycache__.
    - deny specific files in venv/bin (the python executables, pybox_launcher,
      and nosandbox stashes) rather than the whole bin/ directory.  A
      directory-level deny would also block reads, which prevents the kernel from
      exec'ing console scripts whose shebangs point to python3.X (now a symlink
      to pybox_launcher — a real binary, so no double-shebang issue, but the
      file still needs to be readable for the kernel to find the shebang).
      File-level deny blocks writes to the protected files while leaving the rest
      of bin/ readable and writable via the workdir grant.
    - bypass_protection on the venv root — required when the venv is named '.env'
      because deny_shell_configs would otherwise block the entire tree. Safe to
      include unconditionally; it is a no-op for any other venv name.
    """
    venv_str = str(venv_root)

    # Files in bin/ that must never be overwritten by sandboxed code.
    # python_nosandbox is intentionally excluded: it is the inner target that
    # nono execs after the sandbox is established, so replacing it doesn't grant
    # capabilities beyond what the policy already allows.  Including it would
    # prevent nono from exec'ing it (nono treats file-level deny as a permanent
    # restriction on exec, not just open()).
    protected_bin = (
        [f"{venv_str}/bin/{name}" for name in python_exe_names]
        + [
            f"{venv_str}/bin/pybox_launcher",
            f"{venv_str}/bin/pybox_launcher.env",
            f"{venv_str}/bin/pybox_pip_launcher.env",
        ]
    )

    return {
        "meta": {
            "name": "pybox",
            "version": _PYBOX_VERSION,
            "description": (
                "pybox python sandbox: read venv, write only to venv/__pycache__, "
                "read+write $WORKDIR, deny writes to venv/bin python executables and pybox launcher"
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
            "read": [venv_str, "$HOME/.CFUserTextEncoding"],
            "write": [f"{venv_str}/__pycache__"],
            "deny": protected_bin,
            "bypass_protection": [venv_str],
        },
        "environment": {
            "allow_vars": _python_env_allow_vars(),
        },
    }


def _build_pip_profile(venv_root: Path, python_exe_names: list[str]) -> dict:
    """
    Build the nono profile dict for the pip* launcher.

    Policy differences from the python profile:
    - workdir: read only — pip has no reason to write into the project tree.
    - venv/bin is writable so pip can install console-script entrypoints.
    - Individual python executables, pybox_launcher, python_nosandbox, and
      pip_nosandbox are explicitly denied so pip cannot overwrite the interpreter
      or launcher even though the rest of bin/ is writable.
    - lib, lib64, include, share, __pycache__, pip-cache are all writable
      for normal package installation.
    """
    venv_str = str(venv_root)

    # Files in bin/ that must never be overwritten by pip.
    protected_bin = (
        [f"{venv_str}/bin/{name}" for name in python_exe_names]
        + [
            f"{venv_str}/bin/pybox_launcher",
            f"{venv_str}/bin/pybox_launcher.env",
            f"{venv_str}/bin/pybox_pip_launcher.env",
            f"{venv_str}/bin/python_nosandbox",
            f"{venv_str}/bin/pip_nosandbox",
        ]
    )

    return {
        "meta": {
            "name": "pybox-pip",
            "version": _PYBOX_VERSION,
            "description": (
                "pybox pip sandbox: read $WORKDIR, write to venv for installs, "
                "deny writes to venv/bin python executables and pybox launcher"
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
        "environment": {
            "allow_vars": _pip_env_allow_vars(),
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

    # Stash files live directly in bin/ (not a subdirectory) so that CPython's
    # pyvenv.cfg discovery works correctly.  CPython looks for pyvenv.cfg one
    # directory above sys.executable (using the unresolved argv[0] path).
    # If the stash were in bin/nosandbox/, argv[0] would be bin/nosandbox/python
    # and CPython would look in bin/ for pyvenv.cfg — not found.  With the stash
    # directly in bin/, argv[0] is bin/python_nosandbox and CPython looks in
    # venv/ — where pyvenv.cfg actually lives.
    python_nosandbox = bin_dir / "python_nosandbox"
    pip_nosandbox = bin_dir / "pip_nosandbox"
    launcher = bin_dir / "pybox_launcher"  # sentinel and symlink target

    print(f"pybox: setting up sandbox in {venv_root}", file=sys.stderr)

    # Safety check: venv path must be embeddable in JSON and config files.
    _validate_venv_path(venv_root)

    # --- nono availability check ---
    # Launcher and configs are written regardless so they are ready once nono
    # is installed.
    if shutil.which("nono") is None:
        print(
            "pybox: warning: nono is not installed or not on PATH.\n"
            "pybox: Sandbox launcher will be installed but will fail until nono is available.\n"
            "pybox: See https://nono.sh for installation instructions.",
            file=sys.stderr,
        )

    # --- collect symlinks to rewire BEFORE creating stash files ---
    # _find_symlinks_for compares resolved paths, so python_nosandbox (which will
    # also resolve to real_python) must not exist yet when we scan — otherwise it
    # would be included in the list and get rewired to the launcher, defeating its
    # purpose.
    python_symlinks = _find_symlinks_for(bin_dir, real_python)

    # --- install the native launcher binary ---
    _install_launcher_binary(bin_dir)

    # --- write python launcher config ---
    _write_python_launcher_env(bin_dir, venv_root, python_nosandbox)

    # --- pip (optional) ---
    # Two cases:
    # 1. pip is a symlink to a real pip binary (conda / pyenv style).
    #    Stash the binary as bin/pip_nosandbox, write a pip launcher config.
    # 2. pip is a console-script (plain file, shebang = this venv's python).
    #    Copy to bin/pip_nosandbox rewriting its shebang to python_nosandbox
    #    so it still works after python is rewired, then replace the original
    #    with a symlink to pybox_launcher.
    pip_symlinks: list[Path] = []
    real_pip: Path | None = None
    pip_scripts: list[Path] = []  # console-script pip* files
    pip_was_symlink: bool = False  # captured before rewiring; used at stash time
    pip_script_content: bytes | None = None  # captured before rewiring for Case 2

    pip_bin = bin_dir / "pip"
    if pip_bin.is_symlink():
        # Case 1: symlink to a standalone pip binary
        pip_was_symlink = True
        real_pip = pip_bin.resolve()
        pip_symlinks = _find_symlinks_for(bin_dir, real_pip)
        _write_pip_launcher_env(bin_dir, venv_root, pip_nosandbox)
    else:
        # Case 2: console-script pip* files (shebang → this venv's python)
        pip_scripts = _find_pip_scripts(bin_dir, real_python)
        if pip_scripts:
            _write_pip_launcher_env(bin_dir, venv_root, pip_nosandbox)
            real_pip = pip_nosandbox  # marks pip as present for profile/commit logic
            # Read the canonical pip script content NOW, before rewiring turns it
            # into a symlink to pybox_launcher.
            canonical = bin_dir / "pip"
            pip_source = canonical if canonical in pip_scripts else sorted(pip_scripts)[0]
            pip_script_content = pip_source.read_bytes()

    # --- nono profiles ---
    # Written to <venv>/share/pybox/ with absolute hardcoded venv paths so
    # they are correct regardless of the user's working directory at runtime.
    profile_dir = venv_root / "share" / "pybox"
    profile_dir.mkdir(parents=True, exist_ok=True)

    python_exe_names = _python_exe_names(bin_dir, real_python)

    python_profile = _build_python_profile(venv_root, python_exe_names)
    pip_profile = _build_pip_profile(venv_root, python_exe_names)

    # pip profile first, python profile second (mirrors the symlink commit order).
    if real_pip is not None:
        _write_profile(profile_dir, "pybox_pip_profile.json", pip_profile)
    _write_profile(profile_dir, "pybox_profile.json", python_profile)

    print(f"pybox: nono profiles written to {profile_dir}", file=sys.stderr)

    # --- rewire python symlinks → pybox_launcher ---
    for link in python_symlinks:
        link.unlink()
        link.symlink_to(launcher)

    # --- rewire pip symlinks (case 1) → pybox_launcher ---
    # pip entry points all point to the same launcher binary; the launcher
    # selects the pip vs python config by reading pybox_pip_launcher.env when
    # argv[0] ends with "pip" (handled in the launcher binary via config file
    # naming convention — both configs live in bin/ alongside the binary).
    for link in pip_symlinks:
        link.unlink()
        link.symlink_to(launcher)

    # --- rewire pip console-scripts (case 2) → pybox_launcher ---
    for script in pip_scripts:
        script.unlink()
        script.symlink_to(launcher)

    # --- create stash files AFTER rewiring so _find_symlinks_for didn't see them ---

    # python_nosandbox: symlink to the real interpreter
    if python_nosandbox.exists() or python_nosandbox.is_symlink():
        python_nosandbox.unlink()
    python_nosandbox.symlink_to(real_python)

    # pip_nosandbox: depends on pip layout
    if pip_was_symlink:
        # Case 1: symlink to the real pip binary
        if pip_nosandbox.exists() or pip_nosandbox.is_symlink():
            pip_nosandbox.unlink()
        pip_nosandbox.symlink_to(real_pip)  # type: ignore[arg-type]
    elif pip_scripts:
        # Case 2: rewrite the canonical pip console-script shebang → python_nosandbox.
        # Use pip_script_content captured before rewiring (the scripts are now symlinks).
        assert pip_script_content is not None
        newline_pos = pip_script_content.index(b"\n")
        new_content = (
            f"#!{python_nosandbox}\n".encode() + pip_script_content[newline_pos + 1:]
        )
        if pip_nosandbox.exists() or pip_nosandbox.is_symlink():
            pip_nosandbox.unlink()
        pip_nosandbox.write_bytes(new_content)
        current = stat.S_IMODE(pip_nosandbox.stat().st_mode)
        pip_nosandbox.chmod(current | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    print("pybox: sandbox launcher installed successfully.", file=sys.stderr)
