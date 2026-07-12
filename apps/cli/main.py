"""Level Factory CLI (TDD 28).

Phase-1 headless orchestration entrypoint. Exit codes (TDD 28.1):
  0 success | 1 non-blocking findings | 2 blocked by validation/approval
  3 configuration error | 4 tool execution failure | 5 internal error | 130 cancelled
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Make the repo root importable (packages/, adapters/, apps/) when run directly.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from apps.cli.commands import (  # noqa: E402
    cmd_accept_exception, cmd_approve, cmd_batch_create, cmd_batch_report,
    cmd_batch_run, cmd_cache, cmd_ci_init, cmd_diagnostics, cmd_doctor,
    cmd_export, cmd_init, cmd_plan, cmd_portability_test, cmd_reject,
    cmd_release, cmd_review, cmd_run, cmd_status, cmd_team_sign,
    cmd_team_status, cmd_validate,
)

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_BLOCKED = 2
EXIT_CONFIG = 3
EXIT_TOOL = 4
EXIT_INTERNAL = 5
EXIT_CANCELLED = 130


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="level-factory",
                                description="Level Factory orchestration CLI")
    p.add_argument("-C", "--chdir", default=".", help="workspace directory")
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("init", help="initialize a workspace")
    sp.add_argument("path")
    sp.add_argument("--name", default="")
    sp.add_argument("--project-id", default="")
    sp.set_defaults(func=cmd_init)

    sp = sub.add_parser("doctor", help="check tools and environment")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_doctor)

    sp = sub.add_parser("batch", help="batch operations")
    bsub = sp.add_subparsers(dest="batch_command", required=True)
    bc = bsub.add_parser("create", help="create a batch from batch.json")
    bc.add_argument("batch_json")
    bc.set_defaults(func=cmd_batch_create)

    br = bsub.add_parser("run", help="run a whole batch as one parallel DAG")
    br.add_argument("batch_id")
    br.add_argument("--target", default="presentation",
                    choices=["functional-lock", "dispatch-handoff", "presentation"])
    br.set_defaults(func=cmd_batch_run)

    brp = bsub.add_parser("report", help="write mission + batch summary reports")
    brp.add_argument("batch_id")
    brp.add_argument("--json", action="store_true")
    brp.set_defaults(func=cmd_batch_report)

    sp = sub.add_parser("plan", help="plan a mission pipeline")
    sp.add_argument("mission_id")
    sp.add_argument("--target", default="dispatch-handoff",
                    choices=["functional-lock", "dispatch-handoff", "presentation"])
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_plan)

    sp = sub.add_parser("run", help="run a mission pipeline")
    sp.add_argument("mission_id")
    sp.add_argument("--target", default="dispatch-handoff",
                    choices=["functional-lock", "dispatch-handoff", "presentation"])
    sp.set_defaults(func=cmd_run)

    sp = sub.add_parser("status", help="show mission/job status")
    sp.add_argument("mission_id", nargs="?")
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser("validate", help="show normalized validation for a mission")
    sp.add_argument("mission_id")
    sp.set_defaults(func=cmd_validate)

    sp = sub.add_parser("approve", help="approve a gate")
    sp.add_argument("mission_id")
    sp.add_argument("gate")
    sp.add_argument("--note", default="")
    sp.add_argument("--by", default="cli-user")
    sp.add_argument("--candidate", default="", help="candidate id for candidate_selected")
    sp.set_defaults(func=cmd_approve)

    sp = sub.add_parser("reject", help="reject a gate")
    sp.add_argument("mission_id")
    sp.add_argument("gate")
    sp.add_argument("--reason", default="")
    sp.add_argument("--by", default="cli-user")
    sp.set_defaults(func=cmd_reject)

    sp = sub.add_parser("export", help="export a portable mission package")
    sp.add_argument("mission_id")
    sp.add_argument("--mode", default="portable-godot",
                    choices=["portable-godot", "pure-shell", "source-authoring"])
    sp.add_argument("--format", default="folder", choices=["folder", "zip"])
    sp.set_defaults(func=cmd_export)

    sp = sub.add_parser("portability-test", help="clean-project portability test")
    sp.add_argument("mission_id")
    sp.add_argument("--mode", default="portable-godot",
                    choices=["portable-godot", "pure-shell", "source-authoring"])
    sp.set_defaults(func=cmd_portability_test)

    sp = sub.add_parser("team-sign", help="record one approver's sign-off on a gate")
    sp.add_argument("mission_id")
    sp.add_argument("gate")
    sp.add_argument("--by", required=True)
    sp.add_argument("--note", default="")
    sp.set_defaults(func=cmd_team_sign)

    sp = sub.add_parser("team-status", help="show a gate's quorum status")
    sp.add_argument("mission_id")
    sp.add_argument("gate")
    sp.set_defaults(func=cmd_team_status)

    sp = sub.add_parser("accept-exception", help="accept a non-blocking issue with a reason")
    sp.add_argument("mission_id")
    sp.add_argument("--issue", required=True, help="issue code or id")
    sp.add_argument("--by", required=True)
    sp.add_argument("--reason", required=True)
    sp.add_argument("--expires", default=None, help="ISO expiration date")
    sp.add_argument("--ticket", default=None, help="follow-up ticket id")
    sp.set_defaults(func=cmd_accept_exception)

    sp = sub.add_parser("review", help="visual before/after comparison of presentation states")
    sp.add_argument("mission_id")
    sp.set_defaults(func=cmd_review)

    sp = sub.add_parser("ci-init", help="write CI templates into the workspace/repo")
    sp.add_argument("--dest", default=None, help="destination root (default: workspace)")
    sp.set_defaults(func=cmd_ci_init)

    sp = sub.add_parser("release", help="tag a batch release in git (local only, no push)")
    sp.add_argument("batch_id")
    sp.add_argument("--tag", required=True)
    sp.add_argument("--message", default="")
    sp.add_argument("--allow-dirty", action="store_true")
    sp.set_defaults(func=cmd_release)

    sp = sub.add_parser("cache", help="cache maintenance")
    sp.add_argument("action", choices=["inspect", "prune"])
    sp.set_defaults(func=cmd_cache)

    sp = sub.add_parser("diagnostics", help="show a job diagnostic bundle")
    sp.add_argument("job_id")
    sp.set_defaults(func=cmd_diagnostics)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        print("cancelled", file=sys.stderr)
        return EXIT_CANCELLED
    except Exception as exc:  # noqa: BLE001 - top-level guard maps to exit codes
        from packages.core.errors import (
            ApprovalBlockedError, ConfigurationError, LevelFactoryError,
        )
        if isinstance(exc, ApprovalBlockedError):
            print(f"blocked: {exc}", file=sys.stderr)
            return EXIT_BLOCKED
        if isinstance(exc, ConfigurationError):
            print(f"configuration error: {exc}", file=sys.stderr)
            return EXIT_CONFIG
        if isinstance(exc, LevelFactoryError):
            print(f"error: {exc}", file=sys.stderr)
            return EXIT_CONFIG
        print(f"internal error: {exc}", file=sys.stderr)
        return EXIT_INTERNAL


if __name__ == "__main__":
    raise SystemExit(main())
