#!/usr/bin/env python3
"""
A2A Invoice Agent - Safe Live Smoke Test Script
==============================================
Validates the live A2A HTTP+JSON 1.0 deployment without exposing credentials,
calling official grading endpoints, or using real financial data.

Usage:
    PowerShell:
        $env:A2A_BEARER_TOKEN = "your-secret-bearer-token"
        python scripts/smoke_test.py

    Optional environment variables:
        A2A_BASE_URL: Defaults to "https://a2a-invoice-agent-kkbk.onrender.com/a2a/"
"""

import os
import sys
import json
import uuid
import time
import urllib.request
import urllib.error
from urllib.parse import urlsplit
from typing import Dict, Any, Tuple, Optional

# Constants & Configuration
DEFAULT_BASE_URL = "https://a2a-invoice-agent-kkbk.onrender.com/a2a/"
TIMEOUT_SECONDS = 30.0
VALID_ACTIONS = {
    "settle_invoice",
    "request_approval",
    "hold_invoice",
    "reject_duplicate",
    "open_exception",
}


def log_info(msg: str):
    print(f"[INFO] {msg}")


def log_pass(msg: str):
    print(f"  \033[92m[PASS]\033[0m {msg}" if sys.platform != "win32" else f"  [PASS] {msg}")


def log_fail(msg: str):
    print(f"  \033[91m[FAIL]\033[0m {msg}" if sys.platform != "win32" else f"  [FAIL] {msg}")


def get_token() -> str:
    """Read token securely from environment variable. Never prints or logs the token."""
    token = os.environ.get("A2A_BEARER_TOKEN") or os.environ.get("BEARER_TOKEN")
    if not token or not token.strip():
        print("\n" + "=" * 70)
        print("ERROR: Missing Bearer Token.")
        print("Please set the A2A_BEARER_TOKEN environment variable before running:")
        print("    PowerShell: $env:A2A_BEARER_TOKEN = 'your-secret-token'")
        print("    Bash/Zsh:   export A2A_BEARER_TOKEN='your-secret-token'")
        print("=" * 70 + "\n")
        sys.exit(1)
    return token.strip()


def get_base_url() -> str:
    """Read base URL from environment or fallback to default production URL."""
    base = os.environ.get("A2A_BASE_URL", DEFAULT_BASE_URL).strip()
    return base if base.endswith("/") else f"{base}/"


def derive_origin(base_url: str) -> str:
    """Derive service origin (scheme://netloc) safely using urllib.parse.urlsplit."""
    parts = urlsplit(base_url.strip())
    return f"{parts.scheme}://{parts.netloc}"


def send_http_request(
    url: str,
    method: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    payload: Optional[Dict[str, Any]] = None,
    timeout: float = TIMEOUT_SECONDS,
) -> Tuple[int, Dict[str, str], Dict[str, Any]]:
    """
    Execute HTTP request with bounded timeout without retrying message ID.
    Returns: (status_code, response_headers, response_json_dict)
    """
    req_headers = headers.copy() if headers else {}
    data_bytes = None
    if payload is not None:
        data_bytes = json.dumps(payload).encode("utf-8")
        req_headers["Content-Type"] = "application/a2a+json"

    req = urllib.request.Request(url, data=data_bytes, headers=req_headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status_code = resp.status
            resp_headers = dict(resp.headers)
            raw_body = resp.read().decode("utf-8")
            data = json.loads(raw_body) if raw_body.strip() else {}
            return status_code, resp_headers, data
    except urllib.error.HTTPError as e:
        status_code = e.code
        resp_headers = dict(e.headers)
        raw_body = e.read().decode("utf-8")
        try:
            data = json.loads(raw_body)
        except Exception:
            data = {"raw_error": raw_body[:200]}
        return status_code, resp_headers, data
    except urllib.error.URLError as e:
        log_fail(f"Network / connection error connecting to {url}: {e.reason}")
        sys.exit(1)


def build_synthetic_claim_batch(batch_id: str, message_id: str) -> Dict[str, Any]:
    """Generate 12 synthetic claim packages with action-determining evidence and decoys."""
    packages = []
    actions_cycle = [
        ("settle_invoice", "within autonomous authority", "[POL-01]", "[REC-11]", "[AUTH-21]"),
        ("request_approval", "outside delegated authority exceeds threshold", "[POL-02]", "[LIM-12]", "[MGR-22]"),
        ("hold_invoice", "payment pauses until stated verification completes", "[POL-03]", "[PAUSE-13]", "[HOLD-23]"),
        ("reject_duplicate", "the same commercial invoice was already paid duplicate payment", "[POL-04]", "[PAID-14]", "[DUP-24]"),
        ("open_exception", "material records conflict and need an exception workflow mismatch", "[POL-05]", "[DISC-15]", "[ERR-25]"),
    ]

    for i in range(12):
        action_name, decisive_text, ref1, ref2, ref3 = actions_cycle[i % len(actions_cycle)]
        pkg_id = f"synth_pkg_{i+1:02d}"
        packages.append({
            "packageId": pkg_id,
            "vendorName": f"Synthetic Test Vendor {i+1} Corp",
            "invoiceNumber": f"SYNTH-INV-2026-{1000 + i}",
            "amountMinor": (i + 1) * 25000,
            "currency": "INR",
            "documentText": (
                "COVER SHEET: Reference [COVER-001]. For historical records only.\n\n"
                f"ACTION PARAGRAPH: This invoice is {decisive_text}. Authoritative verification {ref1} confirms terms. "
                f"Operational record {ref2} and compliance mandate {ref3} apply directly.\n\n"
                "ARCHIVE EXAMPLE: Training decoy [DECOY-999] was resolved in prior audit period."
            ),
        })

    return {
        "message": {
            "messageId": message_id,
            "role": "ROLE_USER",
            "parts": [
                {
                    "mediaType": "application/vnd.ga5.invoice-claim-batch+json",
                    "data": {
                        "batchId": batch_id,
                        "policyRevision": "rev_2026_q4",
                        "packages": packages,
                    },
                }
            ],
        },
        "configuration": {
            "returnImmediately": False,
            "historyLength": 20,
            "acceptedOutputModes": [
                "application/vnd.ga5.invoice-action-proposals+json",
                "application/vnd.ga5.invoice-action-receipts+json",
            ],
        },
    }


def run_smoke_test():
    token = get_token()
    base_url = get_base_url()
    origin_url = derive_origin(base_url)

    print("=" * 70)
    print("A2A INVOICE AGENT - LIVE SMOKE TEST")
    print(f"Target Base URL: {base_url}")
    print(f"Timeout:         {TIMEOUT_SECONDS}s (per call, no auto-retries)")
    print("Security:        Bearer token loaded securely from environment")
    print("Data Mode:       100% Synthetic test packages only (no real financial data)")
    print("=" * 70 + "\n")

    auth_headers = {
        "Authorization": f"Bearer {token}",
        "A2A-Version": "1.0",
        "Content-Type": "application/a2a+json",
    }

    total_checks = 0
    passed_checks = 0

    def check(condition: bool, description: str):
        nonlocal total_checks, passed_checks
        total_checks += 1
        if condition:
            passed_checks += 1
            log_pass(description)
        else:
            log_fail(description)

    # -------------------------------------------------------------
    # Step 0: Public Discovery & Health Checks
    # -------------------------------------------------------------
    log_info("Step 0: Checking Public Discovery & Health...")
    
    # 0a. Healthz
    status_code, _, health_data = send_http_request(f"{origin_url}/healthz")
    check(status_code == 200, f"GET /healthz returned HTTP {status_code}")
    check(health_data.get("status") == "ok", "Healthz status is 'ok'")

    # 0b. Agent Card
    status_code, _, card_data = send_http_request(f"{origin_url}/.well-known/agent-card.json")
    check(status_code == 200, f"GET /.well-known/agent-card.json returned HTTP {status_code}")
    check("name" in card_data and card_data["name"] == "A2A Invoice Agent", "Agent Card name is correct")
    
    interfaces = card_data.get("supportedInterfaces", [])
    check(len(interfaces) >= 1, "Agent Card contains supportedInterfaces")
    if interfaces:
        advertised_url = interfaces[0].get("url", "")
        check("localhost" not in advertised_url, f"Advertised URL is not localhost ({advertised_url})")
        check(advertised_url.startswith("https://"), "Advertised URL uses HTTPS")
        check(interfaces[0].get("protocolBinding") == "HTTP+JSON", "protocolBinding is HTTP+JSON")
        check(interfaces[0].get("protocolVersion") == "1.0", "protocolVersion is 1.0")

    # -------------------------------------------------------------
    # Step 1: Submit Initial Synthetic 12-Package Claim Batch
    # -------------------------------------------------------------
    log_info("\nStep 1: Submitting Initial 12-Package Claim Batch...")
    batch_id = f"smoke_batch_{int(time.time())}"
    msg_id = f"msg_smoke_init_{uuid.uuid4().hex[:8]}"
    initial_payload = build_synthetic_claim_batch(batch_id, msg_id)

    send_endpoint = f"{base_url}message:send"
    status_code, resp_headers, send_data = send_http_request(
        send_endpoint,
        method="POST",
        headers=auth_headers,
        payload=initial_payload,
    )

    check(status_code == 200, f"POST /message:send returned HTTP {status_code}")
    content_type = resp_headers.get("Content-Type", "")
    check("application/a2a+json" in content_type, f"Content-Type is application/a2a+json ({content_type})")

    task = send_data.get("task", {})
    task_id = task.get("id")
    context_id = task.get("contextId")
    task_state = task.get("state")

    check(bool(task_id), f"Task ID assigned: {task_id}")
    check(task_state == "TASK_STATE_INPUT_REQUIRED", f"Task state is TASK_STATE_INPUT_REQUIRED ({task_state})")

    # Validate Artifacts
    artifacts = task.get("artifacts", [])
    check(len(artifacts) == 1, f"Task contains exactly 1 artifact in input-required state (found {len(artifacts)})")
    
    prop_artifact = artifacts[0] if artifacts else {}
    check(
        prop_artifact.get("mediaType") == "application/vnd.ga5.invoice-action-proposals+json",
        "Artifact mediaType is invoice-action-proposals+json",
    )

    # Validate Proposals
    proposals_data = prop_artifact.get("data", {})
    check(proposals_data.get("batchId") == batch_id, f"Proposal batchId matches request ({batch_id})")
    
    proposals = proposals_data.get("proposals", [])
    check(len(proposals) == 12, f"Exactly 12 proposals generated (found {len(proposals)})")

    seen_action_ids = set()
    proposals_valid = True
    for p in proposals:
        act_id = p.get("actionId", "")
        if act_id in seen_action_ids or len(act_id) < 12:
            proposals_valid = False
        seen_action_ids.add(act_id)

        action = p.get("action")
        if action not in VALID_ACTIONS:
            proposals_valid = False

        refs = p.get("evidenceRefs", [])
        if len(refs) != 3 or any("decoy" in r.lower() or "cover" in r.lower() for r in refs):
            proposals_valid = False

        rationale = p.get("rationale", "")
        if not (60 <= len(rationale) <= 1500) or (action not in rationale):
            proposals_valid = False

    check(proposals_valid, "All 12 proposals passed validation (unique actionIds >= 12 chars, 3 evidence refs, 60-1500 char rationales)")

    # -------------------------------------------------------------
    # Step 2: Submit Valid Continuation & Verify Execution Receipts
    # -------------------------------------------------------------
    log_info("\nStep 2: Submitting Continuation Results...")
    if not task_id or not proposals:
        log_fail("Cannot proceed to continuation without valid task_id and proposals.")
        sys.exit(1)

    # Accept 10, Reject 2
    results = []
    for idx, p in enumerate(proposals):
        outcome = "ACCEPTED" if idx < 10 else "REJECTED"
        results.append({
            "packageId": p["packageId"],
            "actionId": p["actionId"],
            "action": p["action"],
            "outcome": outcome,
            "receiptNonce": f"smoke_nonce_{uuid.uuid4().hex[:12]}",
        })

    cont_msg_id = f"msg_smoke_cont_{uuid.uuid4().hex[:8]}"
    continuation_payload = {
        "message": {
            "messageId": cont_msg_id,
            "taskId": task_id,
            "contextId": context_id,
            "role": "ROLE_USER",
            "parts": [
                {
                    "mediaType": "application/vnd.ga5.invoice-action-results+json",
                    "data": {
                        "batchId": batch_id,
                        "results": results,
                    },
                }
            ],
        }
    }

    status_code, _, cont_data = send_http_request(
        send_endpoint,
        method="POST",
        headers=auth_headers,
        payload=continuation_payload,
    )

    check(status_code == 200, f"POST continuation returned HTTP {status_code}")
    completed_task = cont_data.get("task", {})
    completed_state = completed_task.get("state")
    check(completed_state == "TASK_STATE_COMPLETED", f"Task transitioned to TASK_STATE_COMPLETED ({completed_state})")

    # Verify both proposal and receipt artifacts
    comp_artifacts = completed_task.get("artifacts", [])
    check(len(comp_artifacts) == 2, f"Completed task has exactly 2 artifacts (found {len(comp_artifacts)})")

    receipt_artifact = next(
        (a for a in comp_artifacts if a.get("mediaType") == "application/vnd.ga5.invoice-action-receipts+json"),
        None,
    )
    check(receipt_artifact is not None, "Receipt artifact application/vnd.ga5.invoice-action-receipts+json is present")

    if receipt_artifact:
        executions = receipt_artifact.get("data", {}).get("executions", [])
        check(len(executions) == 10, f"Exactly 10 accepted proposals executed in receipt (found {len(executions)})")
        check(
            all(bool(e.get("receiptNonce")) and len(e.get("evidenceRefs", [])) == 3 for e in executions),
            "All receipt executions contain valid receiptNonce and evidence references",
        )

    # -------------------------------------------------------------
    # Step 3: Fetch Task by ID to Confirm Persistent State
    # -------------------------------------------------------------
    log_info("\nStep 3: Confirming Persistence via GET /tasks/{id}...")
    fetch_endpoint = f"{base_url}tasks/{task_id}"
    status_code, _, fetch_data = send_http_request(
        fetch_endpoint,
        method="GET",
        headers={"Authorization": f"Bearer {token}", "A2A-Version": "1.0"},
    )

    check(status_code == 200, f"GET /tasks/{task_id} returned HTTP {status_code}")
    check(fetch_data.get("id") == task_id, "Fetched task ID matches created task ID")
    check(fetch_data.get("state") == "TASK_STATE_COMPLETED", "Persisted task state is TASK_STATE_COMPLETED")

    # -------------------------------------------------------------
    # Summary
    # -------------------------------------------------------------
    print("\n" + "=" * 70)
    print(f"SMOKE TEST SUMMARY: {passed_checks}/{total_checks} checks passed.")
    if passed_checks == total_checks:
        print("ALL SMOKE TEST VERIFICATIONS PASSED SUCCESSFULLY!")
        print("=" * 70 + "\n")
        sys.exit(0)
    else:
        print("SOME VERIFICATIONS FAILED. Check the output above.")
        print("=" * 70 + "\n")
        sys.exit(1)


if __name__ == "__main__":
    run_smoke_test()
