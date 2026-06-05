"""
Post-attack verification: confirms the sandbox launcher is intact and
that the sandbox is still functional after the malicious install.
"""

import pathlib
import subprocess
import sys

venv = pathlib.Path(sys.executable).parent.parent
launcher = venv / "bin" / "pybox_launcher"

errors = []

# 1. Launcher binary still exists and is executable
if not launcher.exists():
    errors.append(f"FAIL: {launcher} does not exist")
else:
    import stat
    mode = launcher.stat().st_mode
    if not (mode & stat.S_IXUSR):
        errors.append(f"FAIL: {launcher} is no longer executable")
    else:
        print(f"PASS: {launcher.name} still exists and is executable")

# 2. python symlink still points to the launcher (not a raw interpreter)
python_bin = venv / "bin" / "python"
target = python_bin.resolve()
if "nosandbox" in str(target):
    errors.append(
        f"FAIL: bin/python resolves to {target} — launcher was bypassed"
    )
else:
    print(f"PASS: bin/python -> {python_bin.readlink()} (still the launcher)")

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
