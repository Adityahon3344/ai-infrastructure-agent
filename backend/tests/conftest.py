import os
import sys
import tempfile

os.environ["APP_SECRET_KEY"] = "test-secret-key-for-pytest"
os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/test.db"
os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
os.environ["AWS_ACCESS_KEY_ID"] = "testing"
os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
# Unit tests sometimes create servers with fake/unreachable IPs (e.g. 10.0.0.1)
# and trigger a real background execution thread against them. Keep the SSH
# connect timeout short in tests so those threads fail fast instead of idling
# for the production-default timeout.
os.environ.setdefault("SSH_CONNECT_TIMEOUT_SECONDS", "2")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient

from app.core.database import Base, engine, init_db
from app.main import app


@pytest.fixture(scope="function", autouse=True)
def _reset_db():
    init_db()
    yield
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_headers(client):
    resp = client.post("/api/auth/register", json={"email": "admin@example.com", "password": "supersecret123"})
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
