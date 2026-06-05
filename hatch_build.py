"""Hatchling build hook: cross-compile the Go launcher for all supported platforms."""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

TARGETS = [
    ("darwin", "arm64"),
    ("darwin", "amd64"),
    ("linux", "amd64"),
    ("linux", "arm64"),
]


class CustomBuildHook(BuildHookInterface):
    def initialize(self, version, build_data):
        go = shutil.which("go")
        if go is None:
            raise RuntimeError(
                "go is required to build pybox but was not found on PATH.\n"
                "Install Go from https://go.dev/dl/"
            )

        launcher_dir = Path(self.root) / "launcher"
        tmp = Path(tempfile.mkdtemp(prefix="pybox-build-"))
        self._tmp = tmp

        for goos, goarch in TARGETS:
            binary_name = f"pybox-launcher-{goos}-{goarch}"
            out = tmp / binary_name
            env = {**os.environ, "GOOS": goos, "GOARCH": goarch, "CGO_ENABLED": "0"}
            subprocess.run(
                [go, "build", "-o", str(out), "."],
                cwd=launcher_dir,
                env=env,
                check=True,
            )
            # Register the compiled binary as a forced include in the wheel.
            # Destination path inside the wheel matches what pyproject.toml expected.
            build_data["force_include"][str(out)] = f"pybox/bin/{binary_name}"

    def finalize(self, version, build_data, artifact_path):
        if hasattr(self, "_tmp") and self._tmp.exists():
            shutil.rmtree(self._tmp, ignore_errors=True)
