"""Risk classification: combines the catalog's baseline risk for each action
with contextual escalation rules (e.g. state=absent on `file` is more
dangerous than state=present; targeting many servers at once raises overall
blast radius) to produce a final plan-level risk level + human-readable
rationale used by the approval engine and the Plan Preview UI."""
from __future__ import annotations

from dataclasses import dataclass, field

from app.catalog.catalog import DESTRUCTIVE_STATE_VALUES, RiskLevel, get_entry
from app.planner.planspec import PlanSpec

_ORDER = {RiskLevel.LOW: 0, RiskLevel.MEDIUM: 1, RiskLevel.HIGH: 2}


@dataclass
class RiskAssessment:
    level: RiskLevel
    reasons: list[str] = field(default_factory=list)
    requires_approval: bool = False
    blast_radius: int = 0  # number of distinct targets affected


def assess_plan(plan: PlanSpec) -> RiskAssessment:
    reasons: list[str] = []
    level = RiskLevel.LOW

    for step in plan.steps:
        entry = get_entry(step.action)
        if entry is None:
            continue
        step_risk = entry.risk
        if step.params.get("state") in DESTRUCTIVE_STATE_VALUES:
            step_risk = RiskLevel.HIGH
            reasons.append(f"'{step.action}' with state={step.params.get('state')!r} is destructive")
        elif entry.risk == RiskLevel.HIGH:
            reasons.append(f"'{step.action}' is inherently high-risk ({entry.description})")
        elif entry.risk == RiskLevel.MEDIUM:
            reasons.append(f"'{step.action}' changes system state ({entry.description})")

        if _ORDER[step_risk] > _ORDER[level]:
            level = step_risk

    blast_radius = len(plan.target.server_ids) if plan.target.kind == "servers" else (1 if plan.target.connection_id else 0)
    if blast_radius > 5 and level == RiskLevel.LOW:
        level = RiskLevel.MEDIUM
        reasons.append(f"Operation touches {blast_radius} servers at once")
    elif blast_radius > 1 and level == RiskLevel.MEDIUM:
        reasons.append(f"Operation touches {blast_radius} servers at once, increasing blast radius")

    requires_approval = level == RiskLevel.HIGH or (level == RiskLevel.MEDIUM and blast_radius > 5)
    return RiskAssessment(level=level, reasons=reasons or ["Read-only / inspection only"], requires_approval=requires_approval, blast_radius=blast_radius)
