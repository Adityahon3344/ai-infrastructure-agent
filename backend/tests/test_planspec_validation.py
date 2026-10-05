import pytest

from app.planner.planspec import PlanSpec, PlanStep, PlanTarget
from app.validation.validator import validate_plan
from app.risk.classifier import assess_plan
from app.catalog.catalog import RiskLevel


def _plan(steps, target_ids=("s1",)):
    return PlanSpec(
        summary="test", intent="install_package",
        target=PlanTarget(kind="servers", server_ids=list(target_ids)),
        steps=steps,
    )


def test_validator_rejects_unknown_action():
    plan = _plan([PlanStep(action="rm_rf_root", description="danger", params={})])
    result = validate_plan(plan)
    assert not result.valid
    assert "not in the allowed catalog" in result.errors[0]


def test_validator_rejects_missing_required_params():
    plan = _plan([PlanStep(action="package", description="install", params={})])  # missing name/state
    result = validate_plan(plan)
    assert not result.valid
    assert any("missing required parameters" in e for e in result.errors)


def test_validator_rejects_empty_target():
    plan = _plan([PlanStep(action="package", description="x", params={"name": "nginx", "state": "present"})], target_ids=())
    result = validate_plan(plan)
    assert not result.valid


def test_valid_plan_passes():
    plan = _plan([PlanStep(action="package", description="install nginx", params={"name": "nginx", "state": "present"})])
    result = validate_plan(plan)
    assert result.valid, result.errors


def test_risk_classification_low_for_readonly():
    plan = _plan([PlanStep(action="check_disk_usage", description="disk", params={})])
    risk = assess_plan(plan)
    assert risk.level == RiskLevel.LOW
    assert not risk.requires_approval


def test_risk_classification_medium_for_install():
    plan = _plan([PlanStep(action="package", description="install nginx", params={"name": "nginx", "state": "present"})])
    risk = assess_plan(plan)
    assert risk.level == RiskLevel.MEDIUM


def test_risk_classification_high_for_destructive_state():
    plan = _plan([PlanStep(action="file", description="delete", params={"path": "/tmp/x", "state": "absent"})])
    risk = assess_plan(plan)
    assert risk.level == RiskLevel.HIGH
    assert risk.requires_approval


def test_risk_classification_high_for_terminate_instances():
    plan = PlanSpec(
        summary="terminate", intent="provision_ec2",
        target=PlanTarget(kind="aws_connection", connection_id="c1"),
        steps=[PlanStep(action="terminate_instances", description="terminate", params={"instance_ids": ["i-123"]})],
    )
    risk = assess_plan(plan)
    assert risk.level == RiskLevel.HIGH
    assert risk.requires_approval


def test_blast_radius_escalates_risk():
    plan = _plan(
        [PlanStep(action="package", description="install nginx", params={"name": "nginx", "state": "present"})],
        target_ids=[f"s{i}" for i in range(10)],
    )
    risk = assess_plan(plan)
    assert risk.blast_radius == 10
