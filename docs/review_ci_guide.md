# Advanced Review & CI Guide (Phase 5)

## Team approvals (quorum)

Gates can require more than one approver. Each sign-off is bound to the gate's
protected-input fingerprint, so a protected change invalidates every sign-off.

```
level-factory team-sign <mission> handoff_approved --by alice
level-factory team-sign <mission> handoff_approved --by bob
level-factory team-status <mission> handoff_approved
```

Final handoff defaults to a quorum of two; other gates default to one. A gate is
satisfied only when enough *distinct, current* approvers have signed.

## Accepted exceptions

A non-blocking issue can be accepted with a written reason. It is tied to the
mission's functional-lock fingerprint and goes stale if that changes (or an
optional expiration passes). Blocking issues can never be accepted.

```
level-factory accept-exception <mission> --issue PACING_LOW --by alice \
  --reason "backtrack padding covers it" [--expires <iso>] [--ticket DELCO-42]
```

## Visual review (before/after)

Compares the mission's presentation preview states (calm / alarm / extraction)
against a saved baseline and writes an HTML + JSON report, then snapshots the
current previews as the next baseline.

```
level-factory review <mission>
# -> .level_factory/review/<mission>/visual_review.html
```

## CI templates

Writes a GitHub Actions workflow and a portable `ci/run.sh` that run
doctor -> batch run -> portability gate -> report:

```
level-factory ci-init [--dest <root>]
```

## Release (source control)

Tags a batch release in git and records commit + tag provenance. It verifies a
clean tree, never pushes, and never rewrites history:

```
level-factory release <batch> --tag v1.0.0-<batch>   # then: git push origin <tag>
```

## What's deferred (TDD 41.3)

- Cloud/distributed workers: the `Worker` seam and a serializable `JobEnvelope`
  ship (`packages/jobs/workers.py`), but no network transport is included.
- Embedded 3D viewport, multi-user web review, comments/mentions, PR automation,
  and remote SCM operations are out of scope.
