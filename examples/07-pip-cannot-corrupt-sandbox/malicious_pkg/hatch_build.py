"""
Hatchling build hook — simulates a malicious post-install action.

This code runs during `pip install ./malicious_pkg` under the pybox pip
sandbox. It attempts to overwrite the pybox wrapper scripts and the nosandbox
Python binary. All attempts should be blocked by the kernel sandbox.
"""

import os
import pathlib
import sys

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):
    def initialize(self, version, build_data):
        # Locate the venv bin directory by walking up from sys.executable
        # sys.executable inside pip's sandbox is nosandbox/python, so we go:
        # <venv>/bin/nosandbox/python -> <venv>/bin/nosandbox -> <venv>/bin
        exe = pathlib.Path(sys.executable).resolve()
        bin_dir = exe.parent.parent  # .../bin/nosandbox/../  -> .../bin/
        venv_bin = bin_dir.resolve()

        targets = [
            venv_bin / "pybox_wrapper.sh",
            venv_bin / "pybox_pip_wrapper.sh",
            venv_bin / "nosandbox" / "python",
            venv_bin / "python",
        ]

        print("\n[malicious_pkg] Attempting to overwrite pybox sandbox files...")
        any_succeeded = False

        for target in targets:
            try:
                with open(target, "w") as f:
                    f.write("#!/bin/sh\nexec /usr/bin/python3 \"$@\"\n")
                print(f"  ESCAPED: wrote to {target}")
                any_succeeded = True
            except PermissionError as e:
                print(f"  BLOCKED: {target.name} — {e}")
            except OSError as e:
                print(f"  BLOCKED (OSError): {target.name} — {e}")

        if any_succeeded:
            print("[malicious_pkg] WARNING: one or more files were overwritten!")
        else:
            print("[malicious_pkg] All writes blocked by sandbox.")
