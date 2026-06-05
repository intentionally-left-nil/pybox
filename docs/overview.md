# pybox: Overview and Motivation

## The Problem

AI agents that use Python as a tool pose serious security risks. When an agent can freely invoke `python` or `pip`, it can:

- **Install malicious packages**: PyPI packages can contain arbitrary code that executes at install time or import time. A compromised or malicious package can exfiltrate data, modify files, or establish persistence.
- **Prompt injection attacks**: Malicious content embedded in files, web pages, or tool outputs can hijack an agent's behavior and cause it to execute harmful code under the guise of legitimate tasks.
- **Accidental or intentional destructive writes**: An agent with unrestricted filesystem write access can delete, overwrite, or corrupt files outside its intended working scope — including configuration files, credentials, or system binaries.
- **Global environment pollution**: `pip install` into a shared environment mutates the global `site-packages` and `__pycache__`, potentially breaking other tools and leaving persistent artifacts after a task completes.
- **Unauditable side effects**: Without restrictions, there is no enforceable boundary on what a Python process can read or write, making it impossible to reason about what an agent session actually touched.

The fundamental issue is one of **trust boundaries**: agents should be treated as untrusted processes, not as trusted users.

## The Solution: pybox

pybox is a pip-installable package that hardens a Python environment for use by AI agents and other untrusted automation.

Once installed into a Python environment, pybox replaces the `python*` and `pip*` executables in `.bin/` with shell wrappers. These wrappers invoke the real interpreter via [nono](https://nono.sh), a syscall-level sandbox, enforcing strict access policies:

- **Write access**: restricted to the current working directory only. The process cannot write to arbitrary filesystem locations, preventing accidental or malicious modification of files outside the task's scope.
- **Read access**: restricted to the environment itself (the virtualenv or conda env). The process cannot read credentials, SSH keys, or other sensitive files from outside the environment.
- **pip isolation**: package installs are scoped to the environment and do not pollute global `__pycache__` or shared site-packages directories. Each environment remains self-contained.

The wrappers are transparent to callers — existing scripts and tools invoke `python` or `pip` as usual, and receive sandboxed execution automatically.

## Design Principles

- **Minimal friction**: pybox is a single `pip install`. No changes to agent code, no custom launchers, no daemon processes.
- **Defense in depth**: pybox does not rely on agent cooperation. Restrictions are enforced at the syscall level by nono, not by instrumentation of the Python runtime.
- **Scoped by default**: the working directory is the only writable location. Agents do exactly what they need to do — and nothing more.
- **Composable**: pybox works with any virtual environment toolchain (venv, conda, pyenv, etc.) and any agent framework.

## Future Directions

Network access filtering is a natural next step. Restricting outbound connections to known-good hosts would prevent exfiltration and limit the blast radius of a compromised package. This is not included in the current design but is architecturally compatible with the nono-based approach.

## Summary

pybox treats Python as an untrusted execution environment by default — which is the correct posture when AI agents are involved. It makes the sandbox the path of least resistance, so that secure execution is automatic rather than opt-in.
