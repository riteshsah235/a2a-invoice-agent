def test_principal_isolation_and_outsider_protection(client, auth_headers, sample_claim_batch_payload):
    """
    Treat every Bearer token as a separate user.
    An authenticated GET /tasks returns only that principal's tasks (outsider receives []).
    An outsider query to /tasks/{id} or cancel returns 404 with generic error body.
    """
    # User A creates a task
    res_a = client.post(
        "/a2a/message:send",
        headers=auth_headers,
        json=sample_claim_batch_payload,
    )
    assert res_a.status_code == 200
    task_a = res_a.json()["task"]
    task_a_id = task_a["id"]

    # User B arrives with a different Bearer token
    user_b_headers = {
        "Authorization": "Bearer outsider-user-b-token",
        "A2A-Version": "1.0",
        "Content-Type": "application/a2a+json",
    }

    # User B lists tasks -> must see empty list!
    list_res_b = client.get("/a2a/tasks", headers=user_b_headers)
    assert list_res_b.status_code == 200
    assert list_res_b.json()["tasks"] == []

    # User B tries to read User A's task -> 404 generic error, no leakage
    read_res_b = client.get(f"/a2a/tasks/{task_a_id}", headers=user_b_headers)
    assert read_res_b.status_code == 404
    assert task_a_id not in read_res_b.text

    # User B tries to cancel User A's task -> 404 generic error
    cancel_res_b = client.post(f"/a2a/tasks/{task_a_id}:cancel", headers=user_b_headers)
    assert cancel_res_b.status_code == 404
    assert task_a_id not in cancel_res_b.text


def test_cancellation_safety_and_terminal_races(client, auth_headers, sample_claim_batch_payload):
    """
    Test safe cancellation:
    1. Non-terminal task can be cancelled -> TASK_STATE_CANCELED
    2. Cancelled task cannot be continued -> returns 409
    3. Completed task cannot be cancelled -> returns 409
    """
    # 1. Cancel non-terminal task
    res = client.post(
        "/a2a/message:send",
        headers=auth_headers,
        json=sample_claim_batch_payload,
    )
    task = res.json()["task"]
    task_id = task["id"]
    context_id = task["contextId"]
    proposals = task["artifacts"][0]["data"]["proposals"]

    cancel_res = client.post(
        f"/a2a/tasks/{task_id}:cancel",
        headers=auth_headers,
    )
    assert cancel_res.status_code == 200
    canceled_task = cancel_res.json()
    assert canceled_task["state"] == "TASK_STATE_CANCELED"

    # 2. Attempt continuation on cancelled task -> must return 409
    continuation_payload = {
        "message": {
            "messageId": "msg_cont_after_cancel",
            "taskId": task_id,
            "contextId": context_id,
            "role": "ROLE_USER",
            "parts": [
                {
                    "mediaType": "application/vnd.ga5.invoice-action-results+json",
                    "data": {
                        "batchId": "batch_test_alpha_01",
                        "results": [
                            {
                                "packageId": proposals[0]["packageId"],
                                "actionId": proposals[0]["actionId"],
                                "action": proposals[0]["action"],
                                "outcome": "ACCEPTED",
                                "receiptNonce": "nonce_after_cancel_01",
                            }
                        ],
                    }
                }
            ]
        }
    }

    cont_res = client.post(
        "/a2a/message:send",
        headers=auth_headers,
        json=continuation_payload,
    )
    assert cont_res.status_code == 409

    # 3. Create another task and complete it first
    payload2 = dict(sample_claim_batch_payload)
    payload2["message"] = dict(sample_claim_batch_payload["message"])
    payload2["message"]["messageId"] = "msg_task_to_complete_first"

    res2 = client.post("/a2a/message:send", headers=auth_headers, json=payload2)
    task2 = res2.json()["task"]
    task2_id = task2["id"]
    proposals2 = task2["artifacts"][0]["data"]["proposals"]

    complete_payload = {
        "message": {
            "messageId": "msg_cont_valid_finish",
            "taskId": task2_id,
            "contextId": task2["contextId"],
            "role": "ROLE_USER",
            "parts": [
                {
                    "mediaType": "application/vnd.ga5.invoice-action-results+json",
                    "data": {
                        "batchId": "batch_test_alpha_01",
                        "results": [
                            {
                                "packageId": proposals2[0]["packageId"],
                                "actionId": proposals2[0]["actionId"],
                                "action": proposals2[0]["action"],
                                "outcome": "ACCEPTED",
                                "receiptNonce": "nonce_valid_finish",
                            }
                        ],
                    }
                }
            ]
        }
    }

    cont2_res = client.post("/a2a/message:send", headers=auth_headers, json=complete_payload)
    assert cont2_res.status_code == 200
    assert cont2_res.json()["task"]["state"] == "TASK_STATE_COMPLETED"

    # Attempt cancel on completed task -> must return 409
    cancel_completed_res = client.post(f"/a2a/tasks/{task2_id}:cancel", headers=auth_headers)
    assert cancel_completed_res.status_code == 409
