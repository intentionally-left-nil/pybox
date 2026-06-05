"""
Post-attack verification: confirms the sandbox wrappers are intact and
that the sandbox is still functional after the malicious install.
"""

import pathlib
import subprocess
import sys

venv = pathlib.Path(sys.executable).resolve().parent.parent
wrapper = venv / "bin" / "pybox_wrapper.sh"

errors = []

# 1. Wrapper script still looks like a pybox wrapper
text = wrapper.read_text()
if "nono run" not in text:
    errors.append(f"FAIL: {wrapper} no longer contains 'nono run'")
else:
    print(f"PASS: {wrapper.name} still references nono run")

# 2. python symlink still points to the wrapper (not a raw interpreter)
python_bin = venv / "bin" / "python"
target = python_bin.resolve()
if "nosandbox" in str(target):
    errors.append(
        f"FAIL: bin/python resolves to {target} — wrapper was bypassed"
    )
else:
    print(f"PASS: bin/python -> {python_bin.readlink()} (still the wrapper)")

# 3. Sandbox is still functional — write outside CWD is blocked
result = subprocess.run(
    [str(venv / "bin" / "python"), "-c",
     "open('/tmp/post-attack-probe.txt', 'w').write('x')"],
    capture_output=True, text=True
)
if result.returncode == 0:
    errors.append("FAIL: sandbox no longer blocking writes to /tmp")
else:
    print("PASS: sandbox still blocks writes to /tmp")

if errors:
    for e in errors:
        print(e)
    sys.exit(1)
else:
    print("\nSandbox integrity verified.")
