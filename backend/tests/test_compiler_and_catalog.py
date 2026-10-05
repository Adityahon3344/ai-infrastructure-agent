import yaml

from app.compiler.compiler import compile_plan
from app.planner.planspec import PlanSpec, PlanStep, PlanTarget
from app.catalog.catalog import list_catalog, get_entry


def test_catalog_lists_entries():
    catalog = list_catalog()
    keys = {c["key"] for c in catalog}
    assert "package" in keys
    assert "run_instances" in keys
    assert get_entry("does_not_exist") is None


def test_compile_ansible_step_produces_valid_yaml():
    plan = PlanSpec(
        summary="x", intent="install_package", target=PlanTarget(kind="servers", server_ids=["s1"]),
        steps=[PlanStep(action="package", description="install nginx", params={"name": "nginx", "state": "present"})],
    )
    compiled = compile_plan(plan)
    assert len(compiled.tasks) == 1
    task = compiled.tasks[0]
    assert task.kind == "ansible"
    parsed = yaml.safe_load(task.payload)
    assert parsed[0]["tasks"][0]["package"] == {"name": "nginx", "state": "present"}


def test_compiled_ansible_steps_use_privilege_escalation_by_default():
    """Regression test: installing packages, managing services, and writing
    files/directories must all run with become:true — without this, every
    real deployment where the SSH user isn't literally root fails with
    'Permission denied' on step 1."""
    for action, params in [
        ("package", {"name": "nginx", "state": "present"}),
        ("systemd", {"name": "nginx", "state": "started"}),
        ("file", {"path": "/opt/myapp", "state": "directory"}),
        ("copy", {"dest": "/opt/myapp/x", "content": "hi"}),
    ]:
        plan = PlanSpec(
            summary="x", intent="install_package", target=PlanTarget(kind="servers", server_ids=["s1"]),
            steps=[PlanStep(action=action, description="x", params=params)],
        )
        compiled = compile_plan(plan)
        parsed = yaml.safe_load(compiled.tasks[0].payload)
        assert parsed[0]["become"] is True, f"{action} should escalate privileges"


def test_setup_facts_gathering_does_not_need_privilege_escalation():
    plan = PlanSpec(
        summary="x", intent="inspect", target=PlanTarget(kind="servers", server_ids=["s1"]),
        steps=[PlanStep(action="setup", description="gather facts", params={})],
    )
    compiled = compile_plan(plan)
    parsed = yaml.safe_load(compiled.tasks[0].payload)
    assert parsed[0]["become"] is False


def test_compile_aws_step():
    plan = PlanSpec(
        summary="x", intent="provision_ec2", target=PlanTarget(kind="aws_connection", connection_id="c1"),
        steps=[PlanStep(action="list_instance_types", description="list types", params={})],
    )
    compiled = compile_plan(plan)
    assert compiled.tasks[0].kind == "aws"
    assert compiled.tasks[0].payload["action"] == "list_instance_types"


def test_compile_docker_step():
    plan = PlanSpec(
        summary="x", intent="deploy", target=PlanTarget(kind="servers", server_ids=["s1"]),
        steps=[PlanStep(action="docker_run", description="run", params={"image": "nginx:latest", "name": "web"})],
    )
    compiled = compile_plan(plan)
    assert compiled.tasks[0].kind == "docker"
    assert "docker run -d --name web nginx:latest" == compiled.tasks[0].payload
