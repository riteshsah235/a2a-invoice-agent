def test_initial_proposals_batch_lifecycle(client, auth_headers, sample_claim_batch_payload):
    """
    Test initial claim batch processing:
    1. Returns 200 with {"task": Task}
    2. State is TASK_STATE_INPUT_REQUIRED
    3. Exactly ONE artifact of mediaType application/vnd.ga5.invoice-action-proposals+json
    4. NO receipt artifact present yet
    5. Exactly 12 proposals with unique actionId (>= 12 chars), facts, exactly 3 evidenceRefs, 60-1500 char rationale
    """
    response = client.post(
        "/a2a/message:send",
        headers=auth_headers,
        json=sample_claim_batch_payload,
    )
    assert response.status_code == 200
    assert "application/a2a+json" in response.headers.get("content-type", "")

    data = response.json()
    assert "task" in data
    task = data["task"]
    assert task["id"]
    assert task["contextId"]
    assert task["state"] == "TASK_STATE_INPUT_REQUIRED"
    assert len(task["history"]) == 1
    assert task["history"][0]["messageId"] == sample_claim_batch_payload["message"]["messageId"]

    # Verify artifacts: exactly one proposal artifact, no receipt artifact
    assert len(task["artifacts"]) == 1
    prop_artifact = task["artifacts"][0]
    assert prop_artifact["mediaType"] == "application/vnd.ga5.invoice-action-proposals+json"
    
    proposals_data = prop_artifact["data"]
    assert proposals_data["batchId"] == "batch_test_alpha_01"
    proposals = proposals_data["proposals"]
    assert len(proposals) == 12

    seen_pkg_ids = set()
    seen_action_ids = set()

    for p in proposals:
        pkg_id = p["packageId"]
        action_id = p["actionId"]
        action = p["action"]
        facts = p["facts"]
        evidence_refs = p["evidenceRefs"]
        rationale = p["rationale"]

        assert pkg_id not in seen_pkg_ids
        seen_pkg_ids.add(pkg_id)

        assert action_id not in seen_action_ids
        seen_action_ids.add(action_id)
        assert len(action_id) >= 12

        assert action in [
            "settle_invoice",
            "request_approval",
            "hold_invoice",
            "reject_duplicate",
            "open_exception",
        ]

        assert facts["vendorName"]
        assert facts["invoiceNumber"]
        assert isinstance(facts["amountMinor"], int)
        assert facts["currency"] == "INR"

        # Exactly 3 decisive bracketed references
        assert len(evidence_refs) == 3
        for ref in evidence_refs:
            assert ref.startswith("[") and ref.endswith("]")
            # Exclude decoys and cover sheets
            assert "cover" not in ref.lower()
            assert "decoy" not in ref.lower()

        # Rationale between 60 and 1500 chars, naming action
        assert 60 <= len(rationale) <= 1500
        assert action in rationale


def test_continuation_results_and_receipt_generation(client, auth_headers, sample_claim_batch_payload):
    """
    Test continuation flow:
    1. Send initial batch -> receive proposals
    2. Send results message with 10 ACCEPTED and 2 REJECTED
    3. Valid continuation transitions task to TASK_STATE_COMPLETED
    4. Receipt artifact added with exactly the 10 accepted executions
    5. Rejected proposals NOT executed
    """
    init_res = client.post(
        "/a2a/message:send",
        headers=auth_headers,
        json=sample_claim_batch_payload,
    )
    assert init_res.status_code == 200
    task = init_res.json()["task"]
    task_id = task["id"]
    context_id = task["contextId"]
    proposals = task["artifacts"][0]["data"]["proposals"]

    # Build grader continuation results
    results = []
    for idx, p in enumerate(proposals):
        outcome = "ACCEPTED" if idx < 10 else "REJECTED"
        results.append({
            "packageId": p["packageId"],
            "actionId": p["actionId"],
            "action": p["action"],
            "outcome": outcome,
            "receiptNonce": f"nonce_unpredictable_{idx:03d}_{p['actionId'][:8]}",
        })

    continuation_payload = {
        "message": {
            "messageId": "msg_continuation_002",
            "taskId": task_id,
            "contextId": context_id,
            "role": "ROLE_USER",
            "parts": [
                {
                    "mediaType": "application/vnd.ga5.invoice-action-results+json",
                    "data": {
                        "batchId": "batch_test_alpha_01",
                        "results": results,
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
    assert cont_res.status_code == 200
    completed_task = cont_res.json()["task"]
    assert completed_task["id"] == task_id
    assert completed_task["state"] == "TASK_STATE_COMPLETED"
    assert len(completed_task["history"]) == 2

    # Must have proposal artifact AND receipt artifact
    assert len(completed_task["artifacts"]) == 2
    assert completed_task["artifacts"][0]["mediaType"] == "application/vnd.ga5.invoice-action-proposals+json"
    assert completed_task["artifacts"][1]["mediaType"] == "application/vnd.ga5.invoice-action-receipts+json"

    receipts_data = completed_task["artifacts"][1]["data"]
    assert receipts_data["batchId"] == "batch_test_alpha_01"
    executions = receipts_data["executions"]
    # Only 10 accepted proposals should be executed!
    assert len(executions) == 10

    for exec_item in executions:
        assert exec_item["receiptNonce"].startswith("nonce_unpredictable_")
        assert exec_item["facts"]["vendorName"]
        assert len(exec_item["evidenceRefs"]) == 3


def test_continuation_validation_strict_rejection(client, auth_headers, sample_claim_batch_payload):
    """Continuation with altered actionId or action must be rejected with 400."""
    init_res = client.post(
        "/a2a/message:send",
        headers=auth_headers,
        json=sample_claim_batch_payload,
    )
    task = init_res.json()["task"]
    proposals = task["artifacts"][0]["data"]["proposals"]

    # Create invalid result with tampered action
    results = [
        {
            "packageId": proposals[0]["packageId"],
            "actionId": proposals[0]["actionId"],
            "action": "open_exception" if proposals[0]["action"] != "open_exception" else "hold_invoice",  # Tampered!
            "outcome": "ACCEPTED",
            "receiptNonce": "nonce_tampered_123",
        }
    ]

    invalid_continuation = {
        "message": {
            "messageId": "msg_bad_cont_01",
            "taskId": task["id"],
            "contextId": task["contextId"],
            "role": "ROLE_USER",
            "parts": [
                {
                    "mediaType": "application/vnd.ga5.invoice-action-results+json",
                    "data": {
                        "batchId": "batch_test_alpha_01",
                        "results": results,
                    }
                }
            ]
        }
    }

    res = client.post(
        "/a2a/message:send",
        headers=auth_headers,
        json=invalid_continuation,
    )
    assert res.status_code == 400
