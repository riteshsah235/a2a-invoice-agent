from app.config import settings
from app.main import app


def test_agent_card_discovery_public(client):
    """GET /.well-known/agent-card.json must be public and conform to A2A 1.0."""
    response = client.get("/.well-known/agent-card.json")
    assert response.status_code == 200
    assert "application/a2a+json" in response.headers.get("content-type", "")

    data = response.json()
    assert data["name"]
    assert data["description"]
    assert data["version"]
    assert isinstance(data["capabilities"], dict)
    
    # Check skills
    assert len(data["skills"]) >= 1
    skill = next((s for s in data["skills"] if s["name"] == "invoice_action_agent"), None)
    assert skill is not None
    assert skill["description"]
    assert len(skill["tags"]) >= 1

    # Check supportedInterfaces in production
    assert len(data["supportedInterfaces"]) >= 1
    interface = data["supportedInterfaces"][0]
    assert interface["protocolBinding"] == "HTTP+JSON"
    assert interface["protocolVersion"] == "1.0"

    # Production Agent Card URL must not be localhost
    assert "localhost" not in interface["url"]
    assert interface["url"].startswith("https://")
    assert interface["url"] == "https://a2a-invoice-agent-kkbk.onrender.com/a2a/"

    # Check input and output modes
    assert "application/vnd.ga5.invoice-claim-batch+json" in data["defaultInputModes"]
    assert "application/vnd.ga5.invoice-action-proposals+json" in data["defaultOutputModes"]
    assert "application/vnd.ga5.invoice-action-receipts+json" in data["defaultOutputModes"]


def test_agent_card_configurable_for_local_dev(client, monkeypatch):
    """Verify that local development URL overrides remain fully supported."""
    monkeypatch.setattr(settings, "BASE_URL", "http://localhost:8000")
    res1 = client.get("/.well-known/agent-card.json")
    assert res1.status_code == 200
    card1 = res1.json()
    assert card1["supportedInterfaces"][0]["url"] == "http://localhost:8000/a2a/"

    monkeypatch.setattr(settings, "BASE_URL", "http://127.0.0.1:9000/a2a/")
    res2 = client.get("/.well-known/agent-card.json")
    assert res2.status_code == 200
    card2 = res2.json()
    assert card2["supportedInterfaces"][0]["url"] == "http://127.0.0.1:9000/a2a/"


def test_expected_routes_registered():
    """Verify that all required endpoints and HTTP methods are registered on the FastAPI app."""
    openapi_paths = app.openapi()["paths"]

    # Core public endpoints
    assert "/.well-known/agent-card.json" in openapi_paths
    assert "get" in openapi_paths["/.well-known/agent-card.json"]

    assert "/healthz" in openapi_paths
    assert "get" in openapi_paths["/healthz"]

    # A2A specification endpoints mounted under /a2a
    assert "/a2a/message:send" in openapi_paths
    assert "post" in openapi_paths["/a2a/message:send"]

    assert "/a2a/tasks/{id}" in openapi_paths
    assert "get" in openapi_paths["/a2a/tasks/{id}"]

    assert "/a2a/tasks" in openapi_paths
    assert "get" in openapi_paths["/a2a/tasks"]

    assert "/a2a/tasks/{id}:cancel" in openapi_paths
    assert "post" in openapi_paths["/a2a/tasks/{id}:cancel"]


def test_a2a_base_url_info_endpoints(client):
    """Verify that visiting /a2a or /a2a/ via browser GET returns 200 OK info rather than 404/error."""
    for path in ["/a2a", "/a2a/"]:
        res = client.get(path)
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        assert "A2A" in data["protocol"]
        assert "/.well-known/agent-card.json" in data["agent_card"]
        assert "POST /a2a/message:send" in data["endpoints"]


def test_double_slash_path_resilience(client, auth_headers):
    """Verify that paths with double slashes (e.g. /a2a//tasks) are normalized and succeed."""
    res = client.get("/a2a//tasks", headers=auth_headers)
    assert res.status_code == 200
    assert "tasks" in res.json()
