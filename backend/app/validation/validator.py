"""
Validates a PlanSpec against the Catalog before it is allowed anywhere near
execution. This is the enforcement point for "AI proposes; validated tools
execute" — every action key, every required parameter, and every target must
check out here or the plan is rejected with a specific, actionable error.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.catalog.catalog import get_entry
from app.planner.planspec import PlanSpec


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def validate_plan(plan: PlanSpec) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []

    if not plan.steps:
        errors.append("Plan has no steps.")

    if plan.target.kind == "servers" and not plan.target.server_ids:
        errors.append("Plan targets 'servers' but no server_ids were resolved. Ask the user to select a server.")

    if plan.target.kind in ("aws_connection", "kubernetes_connection") and not plan.target.connection_id:
        errors.append(f"Plan targets '{plan.target.kind}' but no connection_id was resolved.")

    for i, step in enumerate(plan.steps):
        entry = get_entry(step.action)
        if entry is None:
            errors.append(f"Step {i+1}: action '{step.action}' is not in the allowed catalog. Refusing to execute unknown/arbitrary actions.")
            continue

        missing = [p for p in entry.required_params if p not in step.params]
        if missing:
            errors.append(f"Step {i+1} ({step.action}): missing required parameters: {missing}")

        unknown = [p for p in step.params if p not in entry.required_params and p not in entry.optional_params]
        if unknown:
            warnings.append(f"Step {i+1} ({step.action}): unexpected parameters ignored by compiler: {unknown}")

        if not entry.reversible:
            warnings.append(f"Step {i+1} ({step.action}) is not reversible.")

    return ValidationResult(valid=not errors, errors=errors, warnings=warnings)
