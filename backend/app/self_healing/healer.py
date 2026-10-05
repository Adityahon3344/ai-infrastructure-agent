"""
Controlled self-healing: only diagnoses whose category is explicitly marked
`retryable=True` (see diagnostics/diagnoser.py) may be retried automatically,
and only up to a small fixed number of attempts with a backoff delay. Every
automated recovery attempt is recorded as a job event so it's fully auditable.
Nothing destructive is ever auto-retried.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from app.diagnostics.diagnoser import Diagnosis, diagnose

MAX_AUTO_RETRIES = 2
RETRY_BACKOFF_SECONDS = 5


@dataclass
class RecoveryOutcome:
    attempted: bool
    diagnosis: Diagnosis
    retries_used: int = 0


def maybe_self_heal(run_fn, stdout: str, stderr: str, on_event) -> tuple[RecoveryOutcome, object | None]:
    """`run_fn()` re-executes the exact same failed step. Returns (outcome, last_result_or_None)."""
    diagnosis = diagnose(stdout, stderr)
    if not diagnosis.retryable:
        return RecoveryOutcome(attempted=False, diagnosis=diagnosis), None

    last_result = None
    for attempt in range(1, MAX_AUTO_RETRIES + 1):
        on_event("self_healing_retry", f"Attempt {attempt}/{MAX_AUTO_RETRIES}: {diagnosis.human_explanation} Retrying in {RETRY_BACKOFF_SECONDS}s.")
        time.sleep(RETRY_BACKOFF_SECONDS)
        last_result = run_fn()
        if getattr(last_result, "success", False):
            on_event("self_healing_success", f"Recovered after {attempt} retr{'y' if attempt == 1 else 'ies'}.")
            return RecoveryOutcome(attempted=True, diagnosis=diagnosis, retries_used=attempt), last_result

    on_event("self_healing_exhausted", f"Automatic recovery did not succeed after {MAX_AUTO_RETRIES} attempts. Manual review required.")
    return RecoveryOutcome(attempted=True, diagnosis=diagnosis, retries_used=MAX_AUTO_RETRIES), last_result
