import json

def test_missing_auth_header(client):
    """Missing authorization returns 401."""
    response = client.post(
        "/a2a/message:send",
        headers={"A2A-Version": "1.0", "Content-Type": "application/a2a+json"},
        json={"message": {"messageId": "m1", "role": "ROLE_USER", "parts": []}},
    )
    assert response.status_code == 401


def test_invalid_auth_header_scheme(client):
    """Non-Bearer authorization returns 401."""
    response = client.post(
        "/a2a/message:send",
        headers={
            "Authorization": "Basic dXNlcjpwYXNz",
            "A2A-Version": "1.0",
            "Content-Type": "application/a2a+json",
        },
        json={"message": {"messageId": "m1", "role": "ROLE_USER", "parts": []}},
    )
    assert response.status_code == 401


def test_missing_a2a_version_header(client):
    """Missing A2A-Version header returns 400."""
    response = client.post(
        "/a2a/message:send",
        headers={
            "Authorization": "Bearer valid-token",
            "Content-Type": "application/a2a+json",
        },
        json={"message": {"messageId": "m1", "role": "ROLE_USER", "parts": []}},
    )
    assert response.status_code == 400


def test_invalid_a2a_version_header(client):
    """Unsupported A2A-Version header returns 400."""
    response = client.post(
        "/a2a/message:send",
        headers={
            "Authorization": "Bearer valid-token",
            "A2A-Version": "2.0",
            "Content-Type": "application/a2a+json",
        },
        json={"message": {"messageId": "m1", "role": "ROLE_USER", "parts": []}},
    )
    assert response.status_code == 400


def test_invalid_content_type_header(client):
    """Non-a2a content-type on POST returns 415."""
    response = client.post(
        "/a2a/message:send",
        headers={
            "Authorization": "Bearer valid-token",
            "A2A-Version": "1.0",
            "Content-Type": "text/plain",
        },
        content="some raw text",
    )
    assert response.status_code == 415


def test_payload_size_limit_enforced(client, auth_headers):
    """Payloads exceeding 512 KiB return 413."""
    oversized_data = "x" * (513 * 1024)
    response = client.post(
        "/a2a/message:send",
        headers=auth_headers,
        json={"message": {"messageId": "huge", "role": "ROLE_USER", "parts": [{"mediaType": "text/plain", "data": {"huge": oversized_data}}]}},
    )
    assert response.status_code == 413
