# nono.sh Research Notes

> Source: https://nono.sh/docs/llms.txt

## What is nono?

nono is a **kernel-enforced sandbox CLI and SDK** for AI agents, MCP servers, and LLM workloads. It wraps any command with an OS-level sandbox, enforcing capability-based isolation at the kernel level using:

- **macOS**: Apple's Seatbelt (`sandbox-exec`)
- **Linux**: Landlock LSM (+ optional seccomp-notify)
- **WSL2**: Partial support (see [WSL2 docs](https://nono.sh/docs/cli/internals/wsl2.md))

### Core features

- **Filesystem sandboxing** — precise read/write/deny per path, enforced by the kernel
- **Network control** — block-all, proxy-filtered allowlists, or per-domain rules
- **Credential injection** — API keys loaded from system keystore and injected via reverse proxy; the sandboxed process never sees the real key
- **Atomic rollbacks** — content-addressable filesystem snapshots before each run, restorable afterward
- **Cryptographic audit trail** — tamper-evident session logs with optional Merkle-root signing
- **Trust & attestation** — Sigstore-based signing of instruction files (SKILLS.md, CLAUDE.md, etc.)
- **Profile system** — reusable JSON capability sets with group composition and inheritance

### Why OS-level controls?

Application-level guardrails (e.g. agent system prompts saying "don't touch ~/.ssh") can be bypassed by the agent itself or by prompt injection. nono's enforcements happen in the kernel — no userspace code running inside the sandbox can bypass them.

---

## Installation

See the full guide: https://nono.sh/docs/cli/getting_started/installation.md

---

## Basic Usage

```bash
# Grant read+write access to current directory, run a command
nono run --allow . -- <command> [args...]

# Use a pre-built profile for a known tool
nono run --profile opencode -- opencode
nono run --profile claude-code -- claude

# Use a local profile file (relative or absolute path)
nono run --profile ./nono.json -- <command> [args...]
```

The `--` separator is recommended. Everything after it is the command to sandbox.

---

## Top-level Commands

| Command | Description |
|---|---|
| `nono run` | Run a command inside the sandbox (supervised, default) |
| `nono shell` | Start an interactive shell inside the sandbox |
| `nono wrap` | Apply sandbox and exec into command — no parent process remains (minimal overhead, no proxy support) |
| `nono why` | Check why a path/network operation would be allowed or denied |
| `nono learn` | Discover required filesystem paths and network activity for a command |
| `nono profile` | Create, inspect, compare, and validate profiles |
| `nono ps` / `attach` / `detach` / `stop` / `inspect` / `prune` | Manage live sandbox sessions |
| `nono rollback` | Manage rollback sessions (list, show, restore, verify, cleanup) |
| `nono audit` | View audit trail of past supervised sessions |
| `nono trust` | Sign, verify, and manage instruction file attestation |
| `nono setup` | System setup and verification |

---

## Filesystem Permission Flags

### Directory flags (recursive)

| Flag | Access | Use case |
|---|---|---|
| `--allow` / `-a` | Read + Write | Working dirs, project folders |
| `--read` / `-r` | Read only | Source code, config |
| `--write` / `-w` | Write only | Output dirs, logs |

### File flags (single file only)

| Flag | Access |
|---|---|
| `--allow-file` | Read + Write |
| `--read-file` | Read only |
| `--write-file` | Write only |

### AF_UNIX socket flags

| Flag | Grants |
|---|---|
| `--allow-unix-socket <path>` | `connect()` to a single socket file |
| `--allow-unix-socket-bind <path>` | `connect()` + `bind()` on a single socket |
| `--allow-unix-socket-dir <dir>` | `connect()` to any direct-child socket in dir |
| `--allow-unix-socket-dir-bind <dir>` | `connect()` + `bind()` in dir |
| `--allow-unix-socket-subtree <dir>` | `connect()` to any socket in subtree |
| `--allow-unix-socket-subtree-bind <dir>` | `connect()` + `bind()` in subtree |

### Deny group overrides

```bash
# Punch a hole through a deny group for a specific path
# (path must also be explicitly granted)
nono run --bypass-protection ~/.aws --allow ~/.aws -- my-aws-agent
```

---

## Network Flags

Network is **allowed by default**. Use these flags to restrict it:

| Flag | Description |
|---|---|
| `--block-net` | Block all outbound network |
| `--network-profile <name>` | Host-level filtering via proxy (`minimal`, `developer`, `claude-code`, `codex`, `opencode`, `enterprise`) |
| `--allow-domain <host>` | Add a domain to the proxy allowlist (activates proxy mode) |
| `--allow-domain 'https://host/path/**'` | Restrict to specific path patterns on a domain |
| `--allow-endpoint 'SERVICE:METHOD:PATH'` | Restrict a credential service to specific HTTP method+path patterns |
| `--open-port <N>` | Allow bidirectional localhost TCP IPC on a port |
| `--listen-port <N>` | Allow the sandboxed process to bind/listen on a TCP port |
| `--upstream-proxy <host:port>` | Route through an enterprise/corporate proxy |
| `--upstream-bypass <host>` | Bypass upstream proxy for specific hosts (supports `*.` wildcards) |
| `--proxy-port <N>` | Fix the credential injection proxy port |
| `--trust-proxy-ca` | (macOS) Add proxy TLS CA to system trust store |

---

## Credential Injection Flags

| Flag | Description |
|---|---|
| `--credential <service>` | Enable proxy-based credential injection for a named service (`openai`, `anthropic`, `gemini`, etc.) |
| `--env-credential <account>` | Load credentials from system keystore and inject as env vars |
| `--env-credential-map <ref> <VAR>` | Map a credential reference (`op://`, `apple-password://`, `env://`, `file://`) to an env var |

---

## Profile & Session Flags

| Flag | Description |
|---|---|
| `--profile` / `-p <name>` | Use a named profile |
| `--workdir <dir>` | Working directory for `$WORKDIR` expansion |
| `--allow-cwd` | Skip the CWD-sharing prompt (for non-interactive/CI use) |
| `--dry-run` | Show what capabilities would be granted without running |
| `--detached` | Start supervised session in background; attach later |
| `--name <name>` | Assign a human-readable name to the session |
| `--rollback` | Enable atomic rollback snapshots |
| `--no-rollback` | Disable rollback entirely |
| `--no-audit` | Disable audit trail |
| `--audit-integrity` | Add filesystem-state hashing to audit |
| `--audit-sign-key <ref>` | Sign the completed session audit record |
| `--capability-elevation` | Enable runtime capability elevation (seccomp-notify on Linux) |
| `--rollback-exclude <pattern>` | Exclude a path/pattern from rollback snapshots |
| `--rollback-include <dir>` | Force-include a normally-excluded dir in rollback |
| `--allow-gpu` | Allow GPU compute access (Metal on macOS, DRM/NVIDIA/AMD on Linux) |

---

## Global Options

| Flag | Description |
|---|---|
| `--silent` / `-s` | Suppress all nono output |
| `--theme <name>` | CLI color theme (`mocha`, `latte`, `frappe`, `macchiato`, `tokyo-night`, `minimal`) |
| `--verbose` / `-v` | Increase verbosity (stackable: `-vvv` = trace) |
| `--config` / `-c <path>` | Specify a config file |

---

## `nono why` — Debugging Access

Check whether a path or network operation would be allowed or denied. Useful for both humans and AI agents.

```bash
# Check a sensitive path
nono why --path ~/.ssh/id_rsa --op read
# Output: DENIED - sensitive_path (SSH keys and config)

# Check with simulated capability context
nono why --path ./src --op write --allow .
# Output: ALLOWED - Granted by: --allow .

# JSON output for programmatic use
nono why --json --path ~/.aws --op read

# From inside a sandbox: query own capabilities
nono run --allow-cwd -- nono why --self --path /tmp --op write --json
```

| Flag | Description |
|---|---|
| `--path <path>` | Filesystem path to check |
| `--op read\|write\|readwrite` | Operation to check (default: `read`) |
| `--host <host>` | Network host to check |
| `--port <N>` | Network port (default: 443) |
| `--json` | JSON output |
| `--self` | Query current sandbox state from inside a sandbox |

---

## Sensitive Paths (Always Blocked by Default)

The following are blocked by the `deny_credentials` group in every profile:

- `~/.ssh` — SSH keys
- `~/.aws`, `~/.gcloud`, `~/.azure` — Cloud credentials
- `~/.gnupg` — GPG keys
- `~/.kube`, `~/.docker` — Container credentials
- `~/.zshrc`, `~/.bashrc`, `~/.profile` — Shell configs (may contain secrets)
- `~/.npmrc`, `~/.git-credentials` — Package manager tokens
- macOS Keychain databases, 1Password, browser data, Messages, Mail

---

## Profiles & Groups

Full docs: https://nono.sh/docs/cli/features/profiles-groups.md

### What are profiles?

Profiles are pre-configured capability sets (JSON files) that define what a sandboxed process can access. Instead of specifying flags manually every time:

```bash
# Without profile (verbose)
nono run --allow-cwd --read ~/.claude --read-file ~/.claude/config.json -- claude

# With profile (concise)
nono run --profile claude-code -- claude
```

### Profile locations

| Source | Location | Precedence |
|---|---|---|
| CLI flags | Command line | Highest |
| User profiles | `~/.config/nono/profiles/*.json` or `*.jsonc` | Medium |
| Pack / preset profiles | Installed packs or compiled presets | Base |

### Profile JSON format

```json
{
  "meta": {
    "name": "my-agent",
    "version": "1.0.0",
    "description": "Profile for my custom agent"
  },
  "extends": "default",
  "workdir": {
    "access": "readwrite"
  },
  "groups": {
    "include": ["node_runtime", "python_runtime", "git_config"],
    "exclude": []
  },
  "filesystem": {
    "allow": ["$HOME/.config/my-agent"],
    "read": [],
    "write": [],
    "deny": [],
    "bypass_protection": [],
    "suppress_save_prompt": []
  },
  "network": {
    "block": false,
    "network_profile": "developer",
    "allow_domain": [],
    "credentials": [],
    "open_port": [],
    "listen_port": []
  }
}
```

Comments and trailing commas are supported (JSONC format). Both `.json` and `.jsonc` extensions are accepted.

### Supported environment variables in paths

| Variable | Expands to |
|---|---|
| `$WORKDIR` | Current working directory |
| `$HOME` | User's home directory |
| `$XDG_CONFIG_HOME` | `~/.config` |
| `$XDG_DATA_HOME` | `~/.local/share` |
| `$XDG_CACHE_HOME` | `~/.cache` |
| `$TMPDIR` | System temp directory |
| `$UID` | Current user ID |

### Profile inheritance

Profiles can extend other profiles. Filesystem, groups, and commands sections are **additive** across inheritance.

```json
{
  "extends": "claude-code",
  "meta": { "name": "my-claude" },
  "filesystem": {
    "allow": ["/opt/my-tools"]
  }
}
```

To clear an inherited network profile: set `"network_profile": null` in the child.

### workdir access values

| Value | Meaning |
|---|---|
| `"none"` | No automatic CWD access (default) |
| `"read"` | Read-only |
| `"write"` | Write-only |
| `"readwrite"` | Full read+write |

---

## Groups

Groups are named, composable collections of security rules. Profiles reference them in `groups.include`.

### Group taxonomy

| Field | Meaning |
|---|---|
| `allow.read` | Read-only access to listed paths |
| `allow.write` | Write-only access |
| `allow.readwrite` | Full read+write access |
| `deny.access` | Block both read and write |
| `deny.unlink` | Block file deletion globally |
| `deny.commands` | Block execution of listed commands (startup-only, deprecated v0.33) |

### Built-in groups (32 total)

**Deny groups** (always active in `default` profile):
- `deny_credentials` — SSH, cloud creds, GPG, container/package tokens
- `deny_keychains_macos` / `deny_keychains_linux`
- `deny_browser_data_macos` / `deny_browser_data_linux`
- `deny_macos_private` — Messages, Mail, Cookies, MobileSync
- `deny_shell_history` — `.bash_history`, `.zsh_history`, etc.
- `deny_shell_configs` — `.bashrc`, `.zshrc`, `.profile`, `.env`

**Protection groups:**
- `unlink_protection` — Prevents file deletion
- `dangerous_commands` — Blocks `rm`, `dd`, `chmod`, `sudo`, `pip`, `npm`, `kill`, etc. (startup-only; deprecated v0.33)
- `dangerous_commands_macos` / `dangerous_commands_linux`

**System path groups:**
- `system_read_macos` / `system_read_linux` — System libraries, dyld cache
- `system_write_macos` / `system_write_linux` — Temp dirs, cache paths
- `user_caches_macos` — `~/Library/Caches`, Preferences
- `user_caches_linux` — `~/.cache`, `~/.local/state`

**Runtime groups (language toolchains):**
- `node_runtime` — nvm, fnm, npm, pnpm, volta
- `rust_runtime` — rustup, cargo
- `python_runtime` — pyenv, conda, pip, uv
- `go_runtime` — `~/go`, `/usr/local/go`
- `nix_runtime` — Nix profile paths, `/nix/store`
- `user_tools` — Local bins, completions
- `homebrew` — `/opt/homebrew` (macOS only)

**Tool-specific groups:**
- `claude_code_macos` / `claude_code_linux`
- `claude_cache_linux`
- `codex_macos`
- `opencode_linux` — `~/.opencode/bin`
- `vscode_macos` / `vscode_linux`
- `git_config`

### Group composition formula

```
((default_groups + groups.include) - groups.exclude)
  + filesystem.{allow,read,write}
  - (deny_groups + filesystem.deny)
  + filesystem.bypass_protection
  + CLI flags   ← highest precedence
```

---

## Creating a Profile

Full docs: https://nono.sh/docs/cli/features/profile-authoring.md

### Step-by-step workflow

```bash
# 1. Scaffold
nono profile init my-agent --extends default --groups deny_credentials --full

# 2. Edit in your editor (with JSON Schema autocomplete)
$EDITOR ~/.config/nono/profiles/my-agent.json

# 3. Validate
nono profile validate ~/.config/nono/profiles/my-agent.json

# 4. Inspect resolved profile (with group expansion)
nono profile show my-agent

# 5. Compare against a baseline
nono profile diff default my-agent

# 6. Dry-run test
nono run --profile my-agent --dry-run -- my-command

# 7. Use it
nono run --profile my-agent -- my-command
```

### `nono profile` subcommands

| Subcommand | Description |
|---|---|
| `init <name>` | Generate a skeleton profile |
| `list` | List all available profiles |
| `show <name>` | Show fully resolved profile |
| `diff <a> <b>` | Diff two profiles |
| `validate <file>` | Validate a profile JSON file |
| `groups [name]` | List all policy groups or show details for one |
| `schema` | Print the profile JSON Schema |
| `guide` | Print the full authoring guide (useful to paste to an LLM) |

### `nono profile init` flags

| Flag | Description |
|---|---|
| `--extends <base>` | Inherit from a base profile |
| `--groups <g1,g2>` | Pre-populate security groups |
| `--full` | Include all optional sections |
| `--output <path>` | Write to a specific file path |
| `--force` | Overwrite existing file |
| `--description <text>` | Set description |

### JSON Schema for editor autocomplete

```bash
nono profile schema --output nono-profile.schema.json
```

Then add to your profile:
```json
{ "$schema": "./nono-profile.schema.json", ... }
```

---

## Available Preset Profiles

| Profile | Use case | Key groups added |
|---|---|---|
| `default` | Base for all others; no CWD access | All deny groups, system paths |
| `claude-code` | Anthropic Claude Code | `claude_code_*`, `node_runtime`, `rust_runtime`, `python_runtime`, `vscode_*`, `git_config`, `unlink_protection` |
| `codex` | OpenAI Codex CLI | `codex_macos`, `node_runtime`, `rust_runtime`, `python_runtime`, `git_config`, `unlink_protection` |
| `opencode` | OpenCode AI assistant | `user_caches_*`, `node_runtime`, `opencode_linux`, `git_config`, `unlink_protection` |
| `openclaw` | OpenClaw gateway/agents | `node_runtime` |
| `python-dev` | Python development | `python_runtime` + `developer` network profile |
| `node-dev` | Node.js development | `node_runtime` + `developer` network profile |
| `go-dev` | Go development | `go_runtime` + `developer` network profile |
| `rust-dev` | Rust development | `rust_runtime` + `developer` network profile |

---

## Using nono with OpenCode

Full docs: https://nono.sh/docs/cli/clients/opencode.md

```bash
nono run --profile opencode -- opencode
```

The `opencode` profile grants:
- Read+write to CWD, `~/.opencode`, `~/.config/opencode`, `~/.cache/opencode`, `~/.local/share/opencode`, `~/.local/share/opentui`, `/tmp`
- Network enabled (required for AI API calls)

### Store API key securely

```bash
# macOS
security add-generic-password -s "nono" -a "openai_api_key" -w

# Linux
secret-tool store --label="nono: openai_api_key" service nono username openai_api_key

# Then run:
nono run --profile opencode --env-credential openai_api_key -- opencode
```

### Note on Google Gemini

Proxy-based credential injection does **not** work with Gemini (OpenCode routes Gemini directly). Use `--env-credential` instead:

```bash
nono run --profile opencode --env-credential gemini_api_key -- opencode
```

---

## Further Reading

| Topic | URL |
|---|---|
| Installation | https://nono.sh/docs/cli/getting_started/installation.md |
| Quickstart | https://nono.sh/docs/cli/getting_started/quickstart.md |
| CLI Reference (all flags) | https://nono.sh/docs/cli/usage/flags.md |
| Examples | https://nono.sh/docs/cli/usage/examples.md |
| Profiles & Groups | https://nono.sh/docs/cli/features/profiles-groups.md |
| Profile Authoring | https://nono.sh/docs/cli/features/profile-authoring.md |
| Profile Introspection | https://nono.sh/docs/cli/features/profile-introspection.md |
| Networking | https://nono.sh/docs/cli/features/networking.md |
| Credential Injection | https://nono.sh/docs/cli/features/credential-injection.md |
| Atomic Rollbacks | https://nono.sh/docs/cli/features/atomic-rollbacks.md |
| Audit Trail | https://nono.sh/docs/cli/features/audit.md |
| Session Lifecycle | https://nono.sh/docs/cli/features/session-lifecycle.md |
| Trust & Attestation | https://nono.sh/docs/cli/features/trust.md |
| macOS Seatbelt internals | https://nono.sh/docs/cli/internals/seatbelt.md |
| Linux Landlock internals | https://nono.sh/docs/cli/internals/landlock.md |
| Architecture Overview | https://nono.sh/docs/cli/internals/overview.md |
| Security Model | https://nono.sh/docs/cli/internals/security-model.md |
| OpenCode client guide | https://nono.sh/docs/cli/clients/opencode.md |
| Troubleshooting | https://nono.sh/docs/cli/usage/troubleshooting.md |
| Developer Workflows | https://nono.sh/docs/cli/usage/developer-workflows.md |
| Managing Packs | https://nono.sh/docs/cli/features/managing-packs.md |
| Publishing Packs | https://nono.sh/docs/cli/features/package-publishing.md |
| Python SDK | https://nono.sh/docs/python/overview.md |
| Node.js SDK | https://nono.sh/docs/typescript/overview.md |
| Full docs index | https://nono.sh/docs/llms.txt |
