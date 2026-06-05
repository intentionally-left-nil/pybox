"""
Sandbox escape attempts via system Python and shell spawning.

nono's Seatbelt policy covers the entire process tree. Any child process
spawned from within the sandbox inherits the same restrictions — including
processes started via os.system, subprocess, or os.execv.

Exit code: 0 if all escapes were blocked, 1 if any succeeded.
"""

import argparse
import os
import subprocess
import sys
import textwrap

parser = argparse.ArgumentParser()
parser.add_argument("--sentinel", required=True,
                    help="Path to a file outside CWD that must not be modified")
args = parser.parse_args()

SENTINEL = args.sentinel
TARGET = "/tmp/pybox-escaped-by-system-python.txt"

# Code that the spawned interpreter will try to run
EVIL_CODE = textwrap.dedent(f"""\
    with open({TARGET!r}, 'w') as f:
        f.write('escaped')
    import os
    os.remove({SENTINEL!r})
    print('escape succeeded')
""")

results: list[tuple[str, bool, str]] = []
all_blocked = True


def check_escaped() -> bool:
    """Return True if the escape write actually landed."""
    return os.path.exists(TARGET)


def record(name: str, blocked: bool, detail: str) -> None:
    global all_blocked
    results.append((name, blocked, detail))
    if not blocked:
        all_blocked = False


# ── Escape 1: os.system ───────────────────────────────────────────────────────

rc = os.system(f'/usr/bin/python3 -c {EVIL_CODE!r} 2>&1')
if check_escaped():
    record("os.system('/usr/bin/python3 -c ...')", False, "TARGET file was created")
else:
    record("os.system('/usr/bin/python3 -c ...')", True,
           f"Blocked (exit code {rc}, no file created)")

# ── Escape 2: subprocess.run ──────────────────────────────────────────────────

try:
    r = subprocess.run(
        ["/usr/bin/python3", "-c", EVIL_CODE],
        capture_output=True, text=True, timeout=10
    )
    if check_escaped():
        record("subprocess.run(['/usr/bin/python3', ...])", False,
               "TARGET file was created")
    else:
        record("subprocess.run(['/usr/bin/python3', ...])", True,
               f"Blocked (returncode={r.returncode})")
except Exception as e:
    record("subprocess.run(['/usr/bin/python3', ...])", True, f"Exception: {e}")

# ── Escape 3: subprocess via shell=True ───────────────────────────────────────

try:
    r = subprocess.run(
        f"bash -c 'python3 -c {EVIL_CODE!r}'",
        shell=True, capture_output=True, text=True, timeout=10
    )
    if check_escaped():
        record("subprocess.run(shell=True, 'bash -c python3 ...')", False,
               "TARGET file was created")
    else:
        record("subprocess.run(shell=True, 'bash -c python3 ...')", True,
               f"Blocked (returncode={r.returncode})")
except Exception as e:
    record("subprocess.run(shell=True, 'bash -c python3 ...')", True, f"Exception: {e}")

# ── Escape 4: os.execv (process replacement) ─────────────────────────────────
#
# os.execv replaces the current process image with the system Python.
# The replacement process is still supervised by nono and inherits the
# Seatbelt policy — it cannot write outside the sandbox either.
#
# We run this in a subprocess so we can catch its exit code without losing
# our own process.

try:
    r = subprocess.run(
        [sys.executable, "-c",
         f"import os; os.execv('/usr/bin/python3', ['/usr/bin/python3', '-c', {EVIL_CODE!r}])"],
        capture_output=True, text=True, timeout=10
    )
    if check_escaped():
        record("os.execv('/usr/bin/python3', [...])", False, "TARGET file was created")
    else:
        record("os.execv('/usr/bin/python3', [...])", True,
               f"Blocked (returncode={r.returncode})")
except Exception as e:
    record("os.execv('/usr/bin/python3', [...])", True, f"Exception: {e}")

# Clean up any partial escape artifacts
if os.path.exists(TARGET):
    try:
        os.remove(TARGET)
    except OSError:
        pass

# ── Report ────────────────────────────────────────────────────────────────────

print(f"\n{'Escape vector':<50} {'Result'}")
print("─" * 70)
for name, blocked, detail in results:
    status = "BLOCKED" if blocked else "ESCAPED"
    print(f"{name:<50} {status}")
    print(f"  {detail}")

print()
if all_blocked:
    print("All escape attempts blocked. Process tree sandbox held.")
    sys.exit(0)
else:
    print("ERROR: one or more escape attempts succeeded.")
    sys.exit(1)
