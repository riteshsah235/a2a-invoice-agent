import logging
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException, status

from app.models.entities import TaskModel, IdempotencyModel, ProposalModel
from app.schemas.a2a import (
    SendMessageRequest,
    Task,
    A2AMessage,
    ArtifactPart,
)
from app.schemas.invoice import (
    InvoiceProposal,
    ContinuationResultsData,
    ExecutionReceipt,
)
from app.services.decision_engine import DecisionEngine
from app.utils.crypto import canonical_fingerprint, canonical_compact_json

logger = logging.getLogger(__name__)


class TaskService:
    def __init__(self, db: Session):
        self.db = db
        self.decision_engine = DecisionEngine(db)

    def handle_send_message(self, principal_id: str, request: SendMessageRequest) -> Task:
        """
        Handle incoming A2A message with full idempotency, safety, and protocol compliance.
        Supports:
        1. Initial invoice claim batch -> generates proposals in TASK_STATE_INPUT_REQUIRED.
        2. Continuation results -> validates match and executes accepted actions to TASK_STATE_COMPLETED.
        """
        msg = request.message
        message_id = msg.messageId
        fingerprint = canonical_fingerprint(msg.model_dump())

        # 1. Idempotency Check
        existing_idempotency = (
            self.db.query(IdempotencyModel)
            .filter_by(principal_id=principal_id, message_id=message_id)
            .first()
        )
        if existing_idempotency:
            if existing_idempotency.fingerprint == fingerprint:
                # Same principal, same messageId, same semantic content -> return stored Task without re-executing
                return Task(**existing_idempotency.response_json)
            else:
                # Same principal, same messageId, DIFFERENT semantic content -> 409 IDEMPOTENCY_CONFLICT
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="IDEMPOTENCY_CONFLICT",
                )

        # 2. Inspect message parts to determine action type
        batch_part = None
        results_part = None

        for p in msg.parts:
            if p.mediaType == "application/vnd.ga5.invoice-claim-batch+json":
                batch_part = p
            elif p.mediaType == "application/vnd.ga5.invoice-action-results+json":
                results_part = p

        if batch_part is not None:
            return self._handle_initial_batch(principal_id, request, batch_part, fingerprint)
        elif results_part is not None:
            return self._handle_continuation_results(principal_id, request, results_part, fingerprint)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unsupported message part mediaType. Expected claim batch or action results.",
            )

    def _handle_initial_batch(
        self,
        principal_id: str,
        request: SendMessageRequest,
        batch_part: Any,
        fingerprint: str,
    ) -> Task:
        """Process initial claim batch: generate proposals, store task, return TASK_STATE_INPUT_REQUIRED."""
        import uuid
        data = batch_part.data
        batch_id = str(data.get("batchId", f"batch_{uuid.uuid4().hex[:12]}"))
        policy_revision = str(data.get("policyRevision", "1.0"))
        packages = data.get("packages", [])

        if not packages or not isinstance(packages, list):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid claim batch: 'packages' array is missing or empty.",
            )

        task_id = request.message.taskId or f"task_{uuid.uuid4().hex[:16]}"
        context_id = request.message.contextId or f"ctx_{uuid.uuid4().hex[:16]}"

        # Batch decision step (using cache by canonical package content)
        proposals: List[InvoiceProposal] = self.decision_engine.process_batch(
            batch_id=batch_id,
            policy_revision=policy_revision,
            packages=packages,
        )

        proposal_artifact = ArtifactPart(
            mediaType="application/vnd.ga5.invoice-action-proposals+json",
            data={
                "batchId": batch_id,
                "proposals": [p.model_dump() for p in proposals],
            },
        )

        # Build Task object
        history = [request.message.model_dump()]
        artifacts = [proposal_artifact.model_dump()]

        task = Task(
            id=task_id,
            contextId=context_id,
            state="TASK_STATE_INPUT_REQUIRED",
            history=[A2AMessage(**m) for m in history],
            artifacts=[proposal_artifact],
        )

        # Persist task in database
        task_model = TaskModel(
            id=task_id,
            principal_id=principal_id,
            context_id=context_id,
            state="TASK_STATE_INPUT_REQUIRED",
            batch_id=batch_id,
            policy_revision=policy_revision,
            history_json=history,
            artifacts_json=artifacts,
        )
        self.db.add(task_model)

        # Persist individual proposals for continuation validation
        for p in proposals:
            prop_model = ProposalModel(
                principal_id=principal_id,
                task_id=task_id,
                context_id=context_id,
                batch_id=batch_id,
                package_id=p.packageId,
                action_id=p.actionId,
                action=p.action,
                facts_json=p.facts.model_dump(),
                evidence_refs_json=p.evidenceRefs,
                rationale=p.rationale,
            )
            self.db.add(prop_model)

        # Record idempotency
        idempotency_rec = IdempotencyModel(
            principal_id=principal_id,
            message_id=request.message.messageId,
            fingerprint=fingerprint,
            task_id=task_id,
            response_json=task.model_dump(),
        )
        self.db.add(idempotency_rec)

        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            winner = (
                self.db.query(IdempotencyModel)
                .filter_by(principal_id=principal_id, message_id=request.message.messageId)
                .first()
            )
            if winner and winner.fingerprint == fingerprint:
                return Task(**winner.response_json)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="IDEMPOTENCY_CONFLICT",
            )

        return task

    def _handle_continuation_results(
        self,
        principal_id: str,
        request: SendMessageRequest,
        results_part: Any,
        fingerprint: str,
    ) -> Task:
        """Process continuation results: validate strictly, record executions, transition to TASK_STATE_COMPLETED."""
        msg = request.message
        task_id = msg.taskId
        context_id = msg.contextId

        if not task_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Continuation message missing taskId",
            )

        task_model = (
            self.db.query(TaskModel)
            .filter_by(id=task_id, principal_id=principal_id)
            .first()
        )
        if not task_model:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task not found",
            )

        if not context_id or task_model.context_id != context_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Context ID mismatch on continuation",
            )

        if task_model.state == "TASK_STATE_CANCELED":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot continue a canceled task",
            )
        if task_model.state == "TASK_STATE_COMPLETED":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Task already completed",
            )

        # Parse continuation results
        try:
            results_data = ContinuationResultsData(**results_part.data)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Malformed continuation results: {str(e)}",
            )

        if results_data.batchId != task_model.batch_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Batch ID mismatch on continuation",
            )

        # Retrieve stored proposals for validation
        stored_proposals = (
            self.db.query(ProposalModel)
            .filter_by(task_id=task_id, principal_id=principal_id)
            .all()
        )
        proposal_map = {p.package_id: p for p in stored_proposals}

        executions: List[Dict[str, Any]] = []

        for res in results_data.results:
            prop = proposal_map.get(res.packageId)
            if not prop:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Unknown packageId in continuation: {res.packageId}",
                )

            if prop.action_id != res.actionId:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"actionId mismatch for package {res.packageId}",
                )

            if prop.action != res.action:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"action mismatch for package {res.packageId}",
                )

            if not res.receiptNonce:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Missing receiptNonce for package {res.packageId}",
                )

            prop.outcome = res.outcome
            prop.receipt_nonce = res.receiptNonce

            if res.outcome == "ACCEPTED":
                exec_item = {
                    "packageId": res.packageId,
                    "actionId": res.actionId,
                    "action": res.action,
                    "receiptNonce": res.receiptNonce,
                    "facts": prop.facts_json,
                    "evidenceRefs": prop.evidence_refs_json,
                }
                executions.append(exec_item)

        # Build receipt artifact
        receipt_artifact = ArtifactPart(
            mediaType="application/vnd.ga5.invoice-action-receipts+json",
            data={
                "batchId": task_model.batch_id,
                "executions": executions,
            },
        )

        updated_artifacts = list(task_model.artifacts_json) + [receipt_artifact.model_dump()]
        updated_history = list(task_model.history_json) + [request.message.model_dump()]

        # Atomic conditional state transition to TASK_STATE_COMPLETED
        rows_updated = (
            self.db.query(TaskModel)
            .filter(
                TaskModel.id == task_id,
                TaskModel.principal_id == principal_id,
                TaskModel.state == "TASK_STATE_INPUT_REQUIRED",
            )
            .update(
                {
                    TaskModel.state: "TASK_STATE_COMPLETED",
                    TaskModel.artifacts_json: updated_artifacts,
                    TaskModel.history_json: updated_history,
                }
            )
        )

        if rows_updated == 0:
            # Race condition lost to concurrent cancellation or completion
            self.db.rollback()
            latest = self.db.query(TaskModel).filter_by(id=task_id, principal_id=principal_id).first()
            if latest and latest.state == "TASK_STATE_CANCELED":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Cannot continue a canceled task",
                )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Task already completed",
            )

        task = Task(
            id=task_model.id,
            contextId=task_model.context_id,
            state="TASK_STATE_COMPLETED",
            history=[A2AMessage(**m) for m in updated_history],
            artifacts=[ArtifactPart(**a) for a in updated_artifacts],
        )

        # Store idempotency
        idempotency_rec = IdempotencyModel(
            principal_id=principal_id,
            message_id=request.message.messageId,
            fingerprint=fingerprint,
            task_id=task_id,
            response_json=task.model_dump(),
        )
        self.db.add(idempotency_rec)

        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            winner = (
                self.db.query(IdempotencyModel)
                .filter_by(principal_id=principal_id, message_id=request.message.messageId)
                .first()
            )
            if winner and winner.fingerprint == fingerprint:
                return Task(**winner.response_json)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="IDEMPOTENCY_CONFLICT",
            )

        return task

    def get_task(self, principal_id: str, task_id: str) -> Task:
        """Fetch task ensuring principal isolation. Return generic 404 for outsiders."""
        task_model = (
            self.db.query(TaskModel)
            .filter_by(id=task_id, principal_id=principal_id)
            .first()
        )
        if not task_model:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task not found",
            )
        return Task(
            id=task_model.id,
            contextId=task_model.context_id,
            state=task_model.state,
            history=[A2AMessage(**m) for m in task_model.history_json],
            artifacts=[ArtifactPart(**a) for a in task_model.artifacts_json],
        )

    def list_tasks(self, principal_id: str) -> List[Task]:
        """List tasks belonging only to the authenticated principal."""
        tasks = (
            self.db.query(TaskModel)
            .filter_by(principal_id=principal_id)
            .order_by(TaskModel.created_at.desc())
            .all()
        )
        return [
            Task(
                id=t.id,
                contextId=t.context_id,
                state=t.state,
                history=[A2AMessage(**m) for m in t.history_json],
                artifacts=[ArtifactPart(**a) for a in t.artifacts_json],
            )
            for t in tasks
        ]

    def cancel_task(self, principal_id: str, task_id: str) -> Task:
        """
        Cancel task safely using atomic state transition.
        - Non-terminal -> transitions to TASK_STATE_CANCELED.
        - Already CANCELED -> returns Task.
        - Already COMPLETED -> returns 409 conflict (atomic cancel-vs-receipt race).
        - Outsider -> returns 404.
        """
        # Attempt atomic conditional update from TASK_STATE_INPUT_REQUIRED to TASK_STATE_CANCELED
        rows_updated = (
            self.db.query(TaskModel)
            .filter(
                TaskModel.id == task_id,
                TaskModel.principal_id == principal_id,
                TaskModel.state == "TASK_STATE_INPUT_REQUIRED",
            )
            .update({TaskModel.state: "TASK_STATE_CANCELED"})
        )
        self.db.commit()

        if rows_updated == 0:
            # Task was not in TASK_STATE_INPUT_REQUIRED
            task_model = (
                self.db.query(TaskModel)
                .filter_by(id=task_id, principal_id=principal_id)
                .first()
            )
            if not task_model:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Task not found",
                )
            if task_model.state == "TASK_STATE_COMPLETED":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Cannot cancel completed task",
                )
            if task_model.state == "TASK_STATE_CANCELED":
                return Task(
                    id=task_model.id,
                    contextId=task_model.context_id,
                    state=task_model.state,
                    history=[A2AMessage(**m) for m in task_model.history_json],
                    artifacts=[ArtifactPart(**a) for a in task_model.artifacts_json],
                )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot cancel task in state {task_model.state}",
            )

        task_model = (
            self.db.query(TaskModel)
            .filter_by(id=task_id, principal_id=principal_id)
            .first()
        )
        return Task(
            id=task_model.id,
            contextId=task_model.context_id,
            state="TASK_STATE_CANCELED",
            history=[A2AMessage(**m) for m in task_model.history_json],
            artifacts=[ArtifactPart(**a) for a in task_model.artifacts_json],
        )
