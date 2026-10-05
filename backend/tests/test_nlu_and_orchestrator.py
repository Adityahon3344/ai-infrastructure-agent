from app.agent.nlu import parse_intent_rule_based
from app.agent.orchestrator import handle_message
from app.core.database import SessionLocal


def test_parse_install_nginx():
    r = parse_intent_rule_based("Install nginx on my Ubuntu server.")
    assert r.intent == "install_package"
    assert r.package_name == "nginx"


def test_parse_install_docker_all_production():
    r = parse_intent_rule_based("Install Docker on all production servers.")
    assert r.intent == "install_package"
    assert r.package_name == "docker"
    assert "production" in r.target_phrase


def test_parse_restart_nginx_specific_server():
    r = parse_intent_rule_based("Restart nginx on web-server-02.")
    assert r.intent == "manage_service"
    assert r.service_action == "restarted"


def test_parse_create_folder():
    r = parse_intent_rule_based("Create /opt/myapp and deploy my application.")
    assert r.path == "/opt/myapp"


def test_parse_create_bare_path_without_folder_keyword():
    """Regression test: a plain path after 'create' with no 'folder'/'directory'
    wording (exactly the spec's own phrasing pattern) must still resolve to
    create_path, not fall through to 'unknown'."""
    r = parse_intent_rule_based("create /opt/myapp on web-server-02")
    assert r.intent == "create_path"
    assert r.path == "/opt/myapp"
    assert r.target_phrase == "web-server-02"


def test_parse_check_disk_usage():
    r = parse_intent_rule_based("Check disk usage on all production servers.")
    assert r.intent == "inspect"
    assert r.inspect_kind == "disk"


def test_parse_python_version():
    r = parse_intent_rule_based("Install Python 3.12 on all Ubuntu servers.")
    assert r.intent == "install_package"
    assert r.package_name == "python3.12"


def test_orchestrator_offers_add_server_when_none_exist(client, auth_headers):
    db = SessionLocal()
    try:
        result = handle_message(db, user_id=None, conversation_id="conv1", text="install nginx on web-01")
        assert result.needs_server_selection is True
        assert result.server_options == []
    finally:
        db.close()


def test_orchestrator_asks_for_missing_package(client, auth_headers):
    db = SessionLocal()
    try:
        result = handle_message(db, user_id=None, conversation_id="conv1", text="install something on web-01")
        assert result.needs_clarification is True
    finally:
        db.close()


def test_orchestrator_generates_low_risk_plan_without_approval(client, auth_headers):
    r = client.post("/api/servers", json={"name": "web-01", "hostname": "10.0.0.5"}, headers=auth_headers)
    server_id = r.json()["id"]
    r2 = client.post("/api/connections", json={
        "name": "web-01-ssh", "type": "ssh", "config": {"hostname": "10.0.0.5", "port": 22, "username": "root"},
        "password": "irrelevant-for-this-test",
    }, headers=auth_headers)
    conn_id = r2.json()["id"]
    client.patch(f"/api/servers/{server_id}", json={"connection_id": conn_id}, headers=auth_headers)

    db = SessionLocal()
    try:
        result = handle_message(db, user_id=None, conversation_id="conv2", text="check disk usage on web-01", selected_server_ids=[server_id])
        assert result.plan_preview is not None
        assert result.plan_preview["risk_level"] == "low"
        assert result.approval is None  # low risk should not require approval
    finally:
        db.close()


def test_orchestrator_resolves_hyphenated_server_name_end_to_end(client, auth_headers):
    """Regression test for the exact spec example: 'Restart nginx on web-server-02.'
    must resolve to the actual server named web-server-02, not misfire as a
    role-tag search for 'web' servers."""
    r = client.post("/api/servers", json={"name": "web-server-02", "hostname": "10.0.0.30"}, headers=auth_headers)
    server_id = r.json()["id"]
    r2 = client.post("/api/connections", json={
        "name": "web-server-02-ssh", "type": "ssh", "config": {"hostname": "10.0.0.30", "port": 22, "username": "root"},
        "password": "irrelevant",
    }, headers=auth_headers)
    conn_id = r2.json()["id"]
    client.patch(f"/api/servers/{server_id}", json={"connection_id": conn_id}, headers=auth_headers)

    db = SessionLocal()
    try:
        result = handle_message(db, user_id=None, conversation_id="conv3", text="Restart nginx on web-server-02.")
        assert result.plan_preview is not None, result.message
        assert result.plan_preview["targets"][0]["name"] == "web-server-02"
    finally:
        db.close()
    r = client.post("/api/servers", json={"name": "web-02", "hostname": "10.0.0.6"}, headers=auth_headers)
    server_id = r.json()["id"]
    r2 = client.post("/api/connections", json={
        "name": "web-02-ssh", "type": "ssh", "config": {"hostname": "10.0.0.6", "port": 22, "username": "root"},
        "password": "irrelevant",
    }, headers=auth_headers)
    conn_id = r2.json()["id"]
    client.patch(f"/api/servers/{server_id}", json={"connection_id": conn_id}, headers=auth_headers)

    from app.agent.nlu import IntentResult
    from app.agent.orchestrator import build_plan
    from app.validation.validator import validate_plan
    from app.risk.classifier import assess_plan
    from app.servers.models import Server

    db = SessionLocal()
    try:
        server = db.get(Server, server_id)
        # Simulate a destructive request directly against the plan builder pipeline
        from app.planner.planspec import PlanSpec, PlanStep, PlanTarget
        plan = PlanSpec(
            summary="delete app dir", intent="manage_service",
            target=PlanTarget(kind="servers", server_ids=[server.id]),
            steps=[PlanStep(action="file", description="remove app dir", params={"path": "/opt/app", "state": "absent"})],
        )
        assert validate_plan(plan).valid
        risk = assess_plan(plan)
        assert risk.level.value == "high"
        assert risk.requires_approval
    finally:
        db.close()
