"""Subprocess runner (TDD 19).

Rules enforced here:
- commands run as an argument array, never ``shell=True`` (19.1)
- stdout/stderr are streamed and preserved to a per-attempt log (19.1)
- the whole child process *tree* is terminated on cancel/timeout (19.2, 19.4)
- exit codes are captured; optional timeouts enforced

Windows note: process-group termination uses CREATE_NEW_PROCESS_GROUP + a
taskkill /T fallback so Blender/Godot subprocess trees do not orphan.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

_IS_WINDOWS = sys.platform.startswith("win")


@dataclass
class RunResult:
    exit_code: int
    timed_out: bool
    cancelled: bool
    duration_s: float
    log_path: Path


class Cancellation:
    """A simple cooperative cancel token shared with the scheduler."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def is_cancelled(self) -> bool:
        return self._event.is_set()


def _popen_kwargs() -> dict:
    if _IS_WINDOWS:  # pragma: no cover - platform specific
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}  # own process group on POSIX


def _terminate_tree(proc: subprocess.Popen, grace_s: float) -> None:
    if proc.poll() is not None:
        return
    try:
        if _IS_WINDOWS:  # pragma: no cover - platform specific
            proc.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except (ProcessLookupError, OSError, ValueError):
        pass

    deadline = time.monotonic() + grace_s
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            return
        time.sleep(0.05)

    # Hard kill of the whole tree.
    try:
        if _IS_WINDOWS:  # pragma: no cover - platform specific
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True,
            )
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (ProcessLookupError, OSError, ValueError):
        pass


def run_command(
    argv: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str] | None,
    log_path: Path,
    timeout_s: int | None = None,
    grace_s: float = 3.0,
    cancel: Cancellation | None = None,
    poll_interval: float = 0.05,
) -> RunResult:
    """Execute ``argv`` safely and stream output to ``log_path``."""
    if not argv:
        raise ValueError("empty command")
    cwd.mkdir(parents=True, exist_ok=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    full_env = dict(os.environ)
    if env:
        full_env.update({k: str(v) for k, v in env.items()})

    start = time.monotonic()
    timed_out = False
    cancelled = False

    with open(log_path, "w", encoding="utf-8", errors="replace") as log:
        log.write(f"$ {' '.join(argv)}\n(cwd={cwd})\n\n")
        log.flush()
        proc = subprocess.Popen(
            list(argv),
            cwd=str(cwd),
            env=full_env,
            stdout=log,
            stderr=subprocess.STDOUT,
            **_popen_kwargs(),
        )

        deadline = start + timeout_s if timeout_s else None
        while True:
            if proc.poll() is not None:
                break
            now = time.monotonic()
            if cancel is not None and cancel.is_cancelled:
                cancelled = True
                _terminate_tree(proc, grace_s)
                break
            if deadline is not None and now >= deadline:
                timed_out = True
                _terminate_tree(proc, grace_s)
                break
            time.sleep(poll_interval)

        exit_code = proc.wait()
        duration = time.monotonic() - start
        log.write(f"\n\n(exit={exit_code}, duration={duration:.2f}s, "
                  f"timed_out={timed_out}, cancelled={cancelled})\n")

    return RunResult(
        exit_code=exit_code,
        timed_out=timed_out,
        cancelled=cancelled,
        duration_s=duration,
        log_path=log_path,
    )
