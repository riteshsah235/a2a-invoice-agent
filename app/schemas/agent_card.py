from typing import List, Dict, Any
from pydantic import BaseModel, Field


class AgentSkill(BaseModel):
    name: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    tags: List[str] = Field(..., min_length=1)


class SupportedInterface(BaseModel):
    url: str = Field(..., min_length=1)
    protocolBinding: str = "HTTP+JSON"
    protocolVersion: str = "1.0"


class AgentCard(BaseModel):
    name: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    version: str = Field(..., min_length=1)
    capabilities: Dict[str, Any] = Field(default_factory=dict)
    skills: List[AgentSkill]
    supportedInterfaces: List[SupportedInterface]
    defaultInputModes: List[str]
    defaultOutputModes: List[str]
