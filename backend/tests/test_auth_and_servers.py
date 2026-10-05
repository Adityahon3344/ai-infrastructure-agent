def test_register_and_login(client):
    r = client.post("/api/auth/register", json={"email": "a@b.com", "password": "password123"})
    assert r.status_code == 200
    assert r.json()["user"]["role"] == "admin"  # first user bootstraps as admin

    r2 = client.post("/api/auth/login", json={"email": "a@b.com", "password": "password123"})
    assert r2.status_code == 200
    assert "access_token" in r2.json()


def test_no_artificial_server_limit(client, auth_headers):
    # Create many servers well beyond any typical hard-coded cap and verify all succeed.
    for i in range(25):
        r = client.post("/api/servers", json={"name": f"srv-{i}", "hostname": f"10.0.0.{i}"}, headers=auth_headers)
        assert r.status_code == 201, r.text

    r = client.get("/api/servers", headers=auth_headers)
    assert r.status_code == 200
    assert len(r.json()) == 25


def test_server_tag_filtering(client, auth_headers):
    client.post("/api/servers", json={"name": "web-01", "hostname": "10.0.0.1", "environment": "production", "tags": {"role": "web"}}, headers=auth_headers)
    client.post("/api/servers", json={"name": "db-01", "hostname": "10.0.0.2", "environment": "production", "tags": {"role": "database"}}, headers=auth_headers)
    client.post("/api/servers", json={"name": "web-02", "hostname": "10.0.0.3", "environment": "staging", "tags": {"role": "web"}}, headers=auth_headers)

    from app.core.database import SessionLocal
    from app.servers.tag_resolver import resolve_servers

    db = SessionLocal()
    try:
        prod_web = resolve_servers(db, environment="production", tags={"role": "web"})
        assert {s.name for s in prod_web} == {"web-01"}

        all_prod = resolve_servers(db, environment="production")
        assert {s.name for s in all_prod} == {"web-01", "db-01"}
    finally:
        db.close()


def test_hyphenated_hostname_resolves_as_literal_server_name_not_role_tag(client, auth_headers):
    """Regression test: a hostname like 'real-web-01' or 'web-server-02'
    contains the substring 'web', which must NOT cause it to be misread as
    the role tag 'web' — it must resolve to the literal server by name."""
    from app.servers.tag_resolver import parse_target_phrase, resolve_servers
    from app.core.database import SessionLocal

    client.post("/api/servers", json={"name": "web-server-02", "hostname": "10.0.0.20", "environment": "production"}, headers=auth_headers)

    parsed = parse_target_phrase("web-server-02")
    assert parsed["server_names"] == ["web-server-02"]
    assert parsed["tags"] == {}

    parsed2 = parse_target_phrase("real-web-01")
    assert parsed2["server_names"] == ["real-web-01"]

    db = SessionLocal()
    try:
        matches = resolve_servers(db, server_names=parsed["server_names"])
        assert {s.name for s in matches} == {"web-server-02"}
    finally:
        db.close()


def test_descriptive_multiword_phrase_still_uses_tag_matching():
    from app.servers.tag_resolver import parse_target_phrase

    parsed = parse_target_phrase("all production web servers")
    assert parsed["environment"] == "production"
    assert parsed["tags"] == {"role": "web"}
    assert parsed["server_names"] is None


def test_single_token_environment_keyword_resolves_as_environment():
    from app.servers.tag_resolver import parse_target_phrase

    assert parse_target_phrase("production")["environment"] == "production"
    assert parse_target_phrase("staging")["environment"] == "staging"


def test_rbac_viewer_cannot_create_server(client):
    client.post("/api/auth/register", json={"email": "admin@x.com", "password": "password123"})
    r = client.post("/api/auth/register", json={"email": "viewer@x.com", "password": "password123", "role": "viewer"})
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    r2 = client.post("/api/servers", json={"name": "srv", "hostname": "1.2.3.4"}, headers=headers)
    assert r2.status_code == 403
