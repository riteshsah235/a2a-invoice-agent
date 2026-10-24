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

    # Check supportedInterfaces
    assert len(data["supportedInterfaces"]) >= 1
    interface = data["supportedInterfaces"][0]
    assert interface["protocolBinding"] == "HTTP+JSON"
    assert interface["protocolVersion"] == "1.0"
    assert interface["url"].endswith("/a2a")

    # Check input and output modes
    assert "application/vnd.ga5.invoice-claim-batch+json" in data["defaultInputModes"]
    assert "application/vnd.ga5.invoice-action-proposals+json" in data["defaultOutputModes"]
    assert "application/vnd.ga5.invoice-action-receipts+json" in data["defaultOutputModes"]
