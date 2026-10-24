import logging
from typing import Dict, Any
from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.api.deps import (
    verify_a2a_version,
    verify_content_type,
    get_current_principal,
)
from app.schemas.a2a import (
    SendMessageRequest,
    SendMessageResponse,
    ListTasksResponse,
    Task,
)
from app.services.task_service import TaskService

logger = logging.getLogger(__name__)

router = APIRouter(
    dependencies=[
        Depends(verify_a2a_version),
        Depends(verify_content_type),
    ]
)


def a2a_response(content: Dict[str, Any], status_code: int = status.HTTP_200_OK) -> JSONResponse:
    """Helper to return application/a2a+json responses."""
    return JSONResponse(
        content=content,
        status_code=status_code,
        media_type="application/a2a+json",
    )


@router.post("/message:send")
def send_message(
    request: SendMessageRequest,
    principal_id: str = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """
    Handle initial invoice claims batch or continuation results.
    Returns: {"task": Task}
    """
    service = TaskService(db)
    task: Task = service.handle_send_message(principal_id=principal_id, request=request)
    return a2a_response(
        content={"task": task.model_dump()},
        status_code=status.HTTP_200_OK,
    )


@router.get("/tasks/{id}")
def get_task(
    id: str,
    principal_id: str = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """
    Get task by ID.
    Returns: Task
    """
    service = TaskService(db)
    task: Task = service.get_task(principal_id=principal_id, task_id=id)
    return a2a_response(
        content=task.model_dump(),
        status_code=status.HTTP_200_OK,
    )


@router.get("/tasks")
def list_tasks(
    principal_id: str = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """
    List all tasks belonging to the current principal.
    Returns: {"tasks": [Task, ...]}
    """
    service = TaskService(db)
    tasks = service.list_tasks(principal_id=principal_id)
    return a2a_response(
        content={"tasks": [t.model_dump() for t in tasks]},
        status_code=status.HTTP_200_OK,
    )


@router.post("/tasks/{id}:cancel")
def cancel_task(
    id: str,
    principal_id: str = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """
    Cancel a non-terminal task.
    Returns: Task
    """
    service = TaskService(db)
    task: Task = service.cancel_task(principal_id=principal_id, task_id=id)
    return a2a_response(
        content=task.model_dump(),
        status_code=status.HTTP_200_OK,
    )
