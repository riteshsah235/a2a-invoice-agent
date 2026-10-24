import copy
import asyncio
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_concurrent_equivalent_requests(db_session, auth_headers, sample_claim_batch_payload):
    """
    Simultaneously dispatch 5 equivalent requests with the same messageId.
    All 5 requests must return HTTP 200 with the exact same task ID,
    proving concurrent idempotency safety.
    """
    payload = copy.deepcopy(sample_claim_batch_payload)
    payload["message"]["messageId"] = "msg_concurrent_ident_001"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        tasks = [
            ac.post("/a2a/message:send", headers=auth_headers, json=payload)
            for _ in range(5)
        ]
        results = await asyncio.gather(*tasks)

    for res in results:
        assert res.status_code == 200

    first_task_id = results[0].json()["task"]["id"]
    for res in results[1:]:
        assert res.json()["task"]["id"] == first_task_id


@pytest.mark.asyncio
async def test_concurrent_conflicting_idempotent_requests(db_session, auth_headers, sample_claim_batch_payload):
    """
    Two concurrent requests sharing the same messageId but with DIFFERENT payloads.
    Exactly one must return 200 and the other must return 409 IDEMPOTENCY_CONFLICT.
    """
    payload1 = copy.deepcopy(sample_claim_batch_payload)
    payload1["message"]["messageId"] = "msg_concurrent_conflict_001"

    payload2 = copy.deepcopy(sample_claim_batch_payload)
    payload2["message"]["messageId"] = "msg_concurrent_conflict_001"
    payload2["message"]["parts"][0]["data"]["batchId"] = "batch_conflicting_id_diff"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        req1 = ac.post("/a2a/message:send", headers=auth_headers, json=payload1)
        req2 = ac.post("/a2a/message:send", headers=auth_headers, json=payload2)
        results = await asyncio.gather(req1, req2)

    status_codes = sorted([r.status_code for r in results])
    assert status_codes == [200, 409]
    conflict_res = next(r for r in results if r.status_code == 409)
    assert "IDEMPOTENCY_CONFLICT" in conflict_res.text


@pytest.mark.asyncio
async def test_concurrent_cancel_vs_continuation_race(db_session, auth_headers, sample_claim_batch_payload):
    """
    Simultaneous race between receipt continuation and cancellation:
    Exactly one must return 200 and the other must return 409.
    Final task state must be either COMPLETED with receipts or CANCELED with no receipts, never both.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # 1. Create initial task in TASK_STATE_INPUT_REQUIRED
        res = await ac.post("/a2a/message:send", headers=auth_headers, json=sample_claim_batch_payload)
        assert res.status_code == 200
        task = res.json()["task"]
        task_id = task["id"]
        context_id = task["contextId"]
        proposals = task["artifacts"][0]["data"]["proposals"]

        continuation_payload = {
            "message": {
                "messageId": "msg_race_continuation_01",
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
                                    "receiptNonce": "nonce_race_unpredictable_001",
                                }
                            ],
                        }
                    }
                ]
            }
        }

        # Fire cancellation and continuation concurrently
        req_cancel = ac.post(f"/a2a/tasks/{task_id}:cancel", headers=auth_headers)
        req_cont = ac.post("/a2a/message:send", headers=auth_headers, json=continuation_payload)

        results = await asyncio.gather(req_cancel, req_cont)
        cancel_res, cont_res = results[0], results[1]

        status_codes = sorted([cancel_res.status_code, cont_res.status_code])
        assert status_codes == [200, 409]

        # Inspect final state in DB
        final_res = await ac.get(f"/a2a/tasks/{task_id}", headers=auth_headers)
        assert final_res.status_code == 200
        final_task = final_res.json()

        if cancel_res.status_code == 200:
            assert final_task["state"] == "TASK_STATE_CANCELED"
            for art in final_task["artifacts"]:
                assert art["mediaType"] != "application/vnd.ga5.invoice-action-receipts+json"
        else:
            assert final_task["state"] == "TASK_STATE_COMPLETED"
            receipt_arts = [a for a in final_task["artifacts"] if a["mediaType"] == "application/vnd.ga5.invoice-action-receipts+json"]
            assert len(receipt_arts) == 1
