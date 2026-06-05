"""
Secrets protection scenarios for the pybox sandbox.

Attempts to read fake credential files and secret environment variables that
should not be accessible from inside the sandbox.

Exit code: 0 if all accesses were blocked, 1 if any succeeded.
"""

import argparse
import os
import sys

parser = argparse.ArgumentParser()
parser.add_argument("--ssh-key")
parser.add_argument("--aws-creds")
parser.add_argument("--docker-cfg")
parser.add_argument("--gcloud-cfg")
args = parser.parse_args()

results: list[tuple[str, bool, str]] = []  # (name, was_blocked, detail)
all_blocked = True


def attempt_read(label: str, path: str) -> None:
    global all_blocked
    try:
        with open(path) as f:
            content = f.read(80)
        results.append((label, False, f"FAIL — read succeeded: {content!r}"))
        all_blocked = False
    except PermissionError as e:
        results.append((label, True, f"Blocked (PermissionError): {e}"))
    except FileNotFoundError:
        results.append((label, True, "File not found (path did not exist inside sandbox)"))
    except OSError as e:
        results.append((label, True, f"Blocked (OSError {e.errno}): {e}"))


def check_env(label: str, var: str) -> None:
    global all_blocked
    value = os.environ.get(var)
    if value is None:
        results.append((label, True, f"Not present in os.environ (stripped by sandbox)"))
    else:
        results.append((label, False, f"FAIL — visible in os.environ: {value!r}"))
        all_blocked = False


# ── Credential file reads ────────────────────────────────────────────────────

print("\n=== Credential file reads ===\n")

if args.ssh_key:
    attempt_read("SSH private key (~/.ssh/id_rsa_fake)", args.ssh_key)
if args.aws_creds:
    attempt_read("AWS credentials (~/.aws/credentials_fake)", args.aws_creds)
if args.docker_cfg:
    attempt_read("Docker config (~/.docker/config_fake.json)", args.docker_cfg)
if args.gcloud_cfg:
    attempt_read("GCP credentials (~/.config/gcloud/credentials_fake.json)", args.gcloud_cfg)

# ── Environment variable leakage ─────────────────────────────────────────────

print("=== Environment variable leakage ===\n")

check_env("SECRET_API_KEY", "SECRET_API_KEY")
check_env("DATABASE_PASSWORD", "DATABASE_PASSWORD")
check_env("AWS_SECRET_ACCESS_KEY", "AWS_SECRET_ACCESS_KEY")

# ── PYTHONPATH injection ──────────────────────────────────────────────────────

print("=== PYTHONPATH injection ===\n")

pythonpath = os.environ.get("PYTHONPATH")
if pythonpath is None:
    results.append(("PYTHONPATH injection", True,
                    "PYTHONPATH not present in os.environ (blocked by nono)"))
else:
    results.append(("PYTHONPATH injection", False,
                    f"FAIL — PYTHONPATH visible: {pythonpath!r}"))
    all_blocked = False

# ── Report ────────────────────────────────────────────────────────────────────

print(f"\n{'Scenario':<55} {'Result'}")
print("─" * 75)
for name, blocked, detail in results:
    status = "BLOCKED" if blocked else "LEAKED"
    print(f"{name:<55} {status}")
    print(f"  {detail}")

print()
if all_blocked:
    print("All secrets protected. Nothing leaked.")
    sys.exit(0)
else:
    print("ERROR: one or more secrets were accessible. Sandbox failed.")
    sys.exit(1)
