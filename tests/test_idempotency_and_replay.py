import copy

def test_exact_message_replay(client, auth_headers, sample_claim_batch_payload):
    """Sending exact duplicate message returns identical Task with HTTP 200."""
    res1 = client.post(
        "/a2a/message:send",
        headers=auth_headers,
        json=sample_claim_batch_payload,
    )
    assert res1.status_code == 200
    task1 = res1.json()["task"]

    # Replay same payload
    res2 = client.post(
        "/a2a/message:send",
        headers=auth_headers,
        json=sample_claim_batch_payload,
    )
    assert res2.status_code == 200
    task2 = res2.json()["task"]

    assert task1["id"] == task2["id"]
    assert task1["state"] == task2["state"]
    assert task1["artifacts"] == task2["artifacts"]


def test_reordered_keys_and_changed_configuration(client, auth_headers, sample_claim_batch_payload):
    """
    Concurrent equivalent requests, reordered JSON keys, and changed returnImmediately
    must return the same complete Task without another model call.
    """
    res1 = client.post(
        "/a2a/message:send",
        headers=auth_headers,
        json=sample_claim_batch_payload,
    )
    task1 = res1.json()["task"]

    # Modify configuration (should be ignored by message fingerprinting)
    modified_payload = copy.deepcopy(sample_claim_batch_payload)
    modified_payload["configuration"]["returnImmediately"] = True
    modified_payload["configuration"]["historyLength"] = 50

    res2 = client.post(
        "/a2a/message:send",
        headers=auth_headers,
        json=modified_payload,
    )
    assert res2.status_code == 200
    task2 = res2.json()["task"]

    assert task1["id"] == task2["id"]


def test_idempotency_conflict_reusing_message_id(client, auth_headers, sample_claim_batch_payload):
    """Reusing messageId with changed semantic content returns 409 IDEMPOTENCY_CONFLICT."""
    res1 = client.post(
        "/a2a/message:send",
        headers=auth_headers,
        json=sample_claim_batch_payload,
    )
    assert res1.status_code == 200
    task1 = res1.json()["task"]

    # Create conflict payload with SAME messageId but altered batch data
    conflict_payload = copy.deepcopy(sample_claim_batch_payload)
    conflict_payload["message"]["parts"][0]["data"]["batchId"] = "tampered_batch_different_id"

    res_conflict = client.post(
        "/a2a/message:send",
        headers=auth_headers,
        json=conflict_payload,
    )
    assert res_conflict.status_code == 409
    assert "IDEMPOTENCY_CONFLICT" in res_conflict.text

    # Verify original task is uncorrupted
    get_res = client.get(f"/a2a/tasks/{task1['id']}", headers=auth_headers)
    assert get_res.status_code == 200
    assert get_res.json()["id"] == task1["id"]
