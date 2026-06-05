"""
Filesystem attack scenarios against the pybox sandbox.

Three attacks are attempted against sentinel files that exist outside the
working directory. All should be blocked by the kernel sandbox.

Exit code: 0 if all attacks were blocked, 1 if any succeeded.
"""

import os
import pathlib
import shutil
import sys

SENTINEL = pathlib.Path("/tmp/pybox-sentinel.txt")
SENTINEL2 = pathlib.Path("/tmp/pybox-sentinel2.txt")
NEW_FILE = pathlib.Path("/tmp/pybox-new-file.txt")

results: list[tuple[str, bool, str]] = []  # (name, was_blocked, detail)


def attempt(name: str, fn) -> None:
    """Run fn(), record whether the sandbox blocked it."""
    try:
        fn()
        results.append((name, False, "FAIL: write/delete succeeded"))
    except PermissionError as e:
        results.append((name, True, f"Blocked: {e}"))
    except OSError as e:
        # On some platforms the sandbox surfaces as a generic OSError
        results.append((name, True, f"Blocked (OSError): {e}"))


# --- Attack 1: write a brand-new file outside CWD ---
def attack_write_new():
    with open(NEW_FILE, "w") as f:
        f.write("created by sandboxed python")


attempt("Write new file to /tmp", attack_write_new)

# --- Attack 2: overwrite an existing file outside CWD ---
def attack_overwrite():
    with open(SENTINEL, "w") as f:
        f.write("overwritten by sandboxed python")


attempt("Overwrite existing file in /tmp", attack_overwrite)

# --- Attack 3: delete a file outside CWD (unlink syscall) ---
def attack_delete():
    SENTINEL2.unlink()


attempt("Delete file in /tmp (unlink)", attack_delete)

# --- Attack 4: shutil.copy into /tmp ---
def attack_shutil_copy():
    shutil.copy(__file__, "/tmp/pybox-stolen-script.py")


attempt("shutil.copy to /tmp", attack_shutil_copy)

# --- Report ---
print(f"\n{'Attack':<45} {'Result'}")
print("─" * 65)
all_blocked = True
for name, blocked, detail in results:
    status = "BLOCKED" if blocked else "ESCAPED"
    print(f"{name:<45} {status}")
    print(f"  {detail}")
    if not blocked:
        all_blocked = False

print()
if all_blocked:
    print("All attacks blocked. Sandbox held.")
    sys.exit(0)
else:
    print("ERROR: one or more attacks succeeded. Sandbox failed.")
    sys.exit(1)
