from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class MessagePart(BaseModel):
    mediaType: str
    data: Dict[str, Any]


class A2AMessage(BaseModel):
    messageId: str
    role: str = "ROLE_USER"
    parts: List[MessagePart]
    taskId: Optional[str] = None
    contextId: Optional[str] = None


class Configuration(BaseModel):
    returnImmediately: Optional[bool] = False
    historyLength: Optional[int] = 20
    acceptedOutputModes: Optional[List[str]] = None


class SendMessageRequest(BaseModel):
    message: A2AMessage
    configuration: Optional[Configuration] = None


class ArtifactPart(BaseModel):
    mediaType: str
    data: Dict[str, Any]


class Task(BaseModel):
    id: str
    contextId: str
    state: str  # ProtoJSON: TASK_STATE_INPUT_REQUIRED, TASK_STATE_COMPLETED, TASK_STATE_CANCELED
    history: List[A2AMessage] = Field(default_factory=list)
    artifacts: List[ArtifactPart] = Field(default_factory=list)


class SendMessageResponse(BaseModel):
    task: Task


class ListTasksResponse(BaseModel):
    tasks: List[Task]
