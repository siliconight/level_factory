"""Typed errors and normalized failure classes.

Failure classes (TDD 14.1) are the vocabulary the job system uses to describe
why a job stopped. They are stable strings so reports and the UI can group and
color them consistently.
"""
from __future__ import annotations

from dataclasses import dataclass

# Failure classes (TDD 14.1)
CONFIGURATION_ERROR = "configuration_error"
MISSING_DEPENDENCY = "missing_dependency"
INPUT_VALIDATION_ERROR = "input_validation_error"
TOOL_EXIT_FAILURE = "tool_exit_failure"
TIMEOUT = "timeout"
CANCELLED = "cancelled"
OUTPUT_CONTRACT_ERROR = "output_contract_error"
ARTIFACT_HASH_ERROR = "artifact_hash_error"
VALIDATION_BLOCKER = "validation_blocker"
INTERNAL_ERROR = "internal_error"

FAILURE_CLASSES = frozenset(
    {
        CONFIGURATION_ERROR,
        MISSING_DEPENDENCY,
        INPUT_VALIDATION_ERROR,
        TOOL_EXIT_FAILURE,
        TIMEOUT,
        CANCELLED,
        OUTPUT_CONTRACT_ERROR,
        ARTIFACT_HASH_ERROR,
        VALIDATION_BLOCKER,
        INTERNAL_ERROR,
    }
)

# Which failure classes may be retried automatically (only when an adapter
# additionally marks the concrete failure transient — see runner).
_TRANSIENT_ELIGIBLE = frozenset({TOOL_EXIT_FAILURE, TIMEOUT, INTERNAL_ERROR})


def is_transient_eligible(failure_class: str) -> bool:
    return failure_class in _TRANSIENT_ELIGIBLE


@dataclass(frozen=True)
class Failure:
    failure_class: str
    message: str
    detail: str = ""
    transient: bool = False

    def as_dict(self) -> dict:
        return {
            "failure_class": self.failure_class,
            "message": self.message,
            "detail": self.detail,
            "transient": self.transient,
        }


class LevelFactoryError(Exception):
    """Base class for expected, user-facing errors (mapped to CLI exit codes)."""

    failure_class = INTERNAL_ERROR


class ConfigurationError(LevelFactoryError):
    failure_class = CONFIGURATION_ERROR


class MissingDependencyError(LevelFactoryError):
    failure_class = MISSING_DEPENDENCY


class InputValidationError(LevelFactoryError):
    failure_class = INPUT_VALIDATION_ERROR


class OutputContractError(LevelFactoryError):
    failure_class = OUTPUT_CONTRACT_ERROR


class ApprovalBlockedError(LevelFactoryError):
    """A gate blocks progress (missing or stale approval, blocking issue)."""

    failure_class = VALIDATION_BLOCKER


class WorkspaceError(LevelFactoryError):
    failure_class = CONFIGURATION_ERROR
