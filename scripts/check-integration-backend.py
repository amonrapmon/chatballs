"""Run the affected integration tests once per candidate and admin container.

Skaro checks overlap. Each named check requests its original selectors; a single
successful pytest run covers their union. Reuse requires the same clean Git SHA,
the same running backend-admin container, and an intact successful run report.
Failures are never cached. This does not create or start services.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODULES = {
    "identity": (
        "test_work_status", "test_work_status_guards", "test_work_status_concurrency",
        "test_work_status_api", "test_work_status_realtime", "test_work_status_migration",
        "test_supervision", "test_authorization",
    ),
    "conversations": (
        "test_supervisor_access", "test_supervisor_realtime", "test_authorization",
        "test_clients_list", "test_query_budget", "test_realtime", "test_lifecycle",
        "test_chat_extras", "test_transfer_reasons", "test_transfer_journal",
        "test_transfer_guards", "test_transfer_migration", "test_participant_models",
        "test_participant_guards", "test_participant_migration",
        "test_domain_event_models", "test_domain_event_guards",
        "test_domain_event_ordering", "test_domain_event_migration",
        "test_conversation_delete",
    ),
    "notifications": ("test_group_visibility", "test_realtime_fanout"),
}
SELECTORS = [
    f"chatballs/{app}/{module}.py"
    for app, modules in MODULES.items() for module in modules
] + [
    "chatballs/notifications/tests.py::DeliveryTests",
    "chatballs/calls/tests/test_services.py::CallCreationTests",
]
CACHE = ROOT / ".pytest_cache" / "integration-backend"


def run(command: list[str]) -> str:
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    if result.returncode:
        sys.stdout.write(result.stdout)
        sys.stderr.write(result.stderr)
        raise SystemExit(result.returncode)
    return result.stdout.strip()


def covers(requested: str) -> bool:
    return any(requested == item or requested.startswith(item + "::") for item in SELECTORS)


def main() -> None:
    requested = sys.argv[1:]
    if not requested or any(not covers(item) for item in requested):
        raise SystemExit("Request only selectors covered by the affected integration suite.")
    run(["git", "diff", "--exit-code", "HEAD", "--"])
    candidate = run(["git", "rev-parse", "HEAD"])
    container = run(["docker", "compose", "ps", "-q", "backend-admin"])
    if not container or "\n" in container:
        raise SystemExit("Exactly one running backend-admin container is required.")
    key = {"candidate": candidate, "container": container, "selectors": SELECTORS}
    digest = hashlib.sha256(json.dumps(key, sort_keys=True).encode()).hexdigest()
    report_path = CACHE / f"{digest}.json"
    output_path = CACHE / f"{digest}.log"
    if report_path.exists() and output_path.exists():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        actual_hash = hashlib.sha256(output_path.read_bytes()).hexdigest()
        if report.get("key") == key and report.get("exit_code") == 0 and report.get("output_sha256") == actual_hash:
            print(f"Covered by successful real pytest run for {candidate} in {container}.")
            print(f"Report: {report_path}; completed: {report['completed_at']}")
            print("Requested: " + " ".join(requested))
            return
    command = [
        "docker", "compose", "exec", "-T", "backend-admin", "python", "-m",
        "pytest", *SELECTORS, "--reuse-db", "-q",
    ]
    print(f"Running affected suite for {candidate} in {container}.", flush=True)
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    output = result.stdout + result.stderr
    sys.stdout.write(output)
    if result.returncode:
        raise SystemExit(result.returncode)
    # A result cannot validate a candidate that changed while pytest was running.
    run(["git", "diff", "--exit-code", "HEAD", "--"])
    if candidate != run(["git", "rev-parse", "HEAD"]) or container != run(["docker", "compose", "ps", "-q", "backend-admin"]):
        raise SystemExit("Candidate or container changed during verification.")
    CACHE.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(output.encode("utf-8"))
    report = {
        "key": key, "exit_code": 0, "command": command,
        "completed_at": datetime.now(UTC).isoformat(),
        "output_sha256": hashlib.sha256(output_path.read_bytes()).hexdigest(),
    }
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Successful real pytest run recorded: {report_path}")


if __name__ == "__main__":
    main()
