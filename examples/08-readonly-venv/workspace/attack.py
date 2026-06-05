"""
Venv tampering attack scenarios for the pybox sandbox.

The sandbox grants read-only access to the venv tree (except __pycache__).
All attempts to modify the venv from inside a sandboxed Python process should
fail with PermissionError.

Exit code: 0 if all attacks were blocked, 1 if any succeeded.
"""

import argparse
import importlib
import pathlib
import site
import sys

parser = argparse.ArgumentParser()
parser.add_argument("--venv", required=True, help="Path to the venv root")
args = parser.parse_args()

venv = pathlib.Path(args.venv).resolve()

# Locate site-packages inside the venv
site_packages = next(
    (pathlib.Path(p) for p in site.getsitepackages() if str(venv) in p),
    None,
)
if site_packages is None:
    print("Could not locate site-packages inside the venv. Aborting.")
    sys.exit(2)

print(f"Venv:          {venv}")
print(f"site-packages: {site_packages}")
print()

results: list[tuple[str, bool, str]] = []
all_blocked = True


def attempt(name: str, fn) -> None:
    global all_blocked
    try:
        fn()
        results.append((name, False, "FAIL: operation succeeded"))
        all_blocked = False
    except PermissionError as e:
        results.append((name, True, f"Blocked (PermissionError): {e}"))
    except OSError as e:
        results.append((name, True, f"Blocked (OSError {e.errno}): {e}"))


# ── Attack 1: inject a .pth file into site-packages ─────────────────────────
# .pth files are executed on every Python startup — persistent code injection.

pth_target = site_packages / "evil.pth"

def attack_pth():
    pth_target.write_text("import os; os.system('echo PWNED')\n")

attempt("Inject evil.pth into site-packages", attack_pth)

# ── Attack 2: delete a real package file ─────────────────────────────────────

requests_init = site_packages / "requests" / "__init__.py"

def attack_delete():
    requests_init.unlink()

attempt("Delete requests/__init__.py (unlink)", attack_delete)

# ── Attack 3: overwrite a real package file ──────────────────────────────────

def attack_overwrite():
    requests_init.write_text("# backdoored\n")

attempt("Overwrite requests/__init__.py", attack_overwrite)

# ── Attack 4: write an arbitrary file to the venv root ───────────────────────

def attack_venv_root():
    (venv / "injected.txt").write_text("injected\n")

attempt("Write injected.txt to venv root", attack_venv_root)

# ── Attack 5: write to venv/lib directly ─────────────────────────────────────

def attack_venv_lib():
    (site_packages / "surprise.py").write_text("print('surprise')\n")

attempt("Write surprise.py directly to site-packages", attack_venv_lib)

# ── Report ────────────────────────────────────────────────────────────────────

print(f"\n{'Attack':<55} {'Result'}")
print("─" * 75)
for name, blocked, detail in results:
    status = "BLOCKED" if blocked else "ESCAPED"
    print(f"{name:<55} {status}")
    print(f"  {detail}")

# Confirm the venv is undamaged by importing requests
print()
try:
    import importlib.metadata
    import requests
    version = importlib.metadata.version("requests")
    print(f"Post-attack import check: requests {version} — OK")
except ImportError as e:
    print(f"Post-attack import check: FAIL — {e}")
    all_blocked = False

print()
if all_blocked:
    print("Venv integrity intact. All tampering attempts blocked.")
    sys.exit(0)
else:
    print("ERROR: one or more attacks succeeded.")
    sys.exit(1)
