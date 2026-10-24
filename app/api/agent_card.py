from fastapi import APIRouter
from fastapi.responses import JSONResponse
from app.config import settings
from app.schemas.agent_card import AgentCard, AgentSkill, SupportedInterface

router = APIRouter()


@router.get("/.well-known/agent-card.json", response_model=AgentCard)
def get_agent_card():
    """Public Agent Card discovery endpoint (A2A 1.0)."""
    # supportedInterfaces contains the exact submitted base URL
    interface_url = settings.BASE_URL.rstrip("/")

    card = AgentCard(
        name=settings.APP_NAME,
        description=settings.APP_DESCRIPTION,
        version=settings.APP_VERSION,
        capabilities={
            "streaming": False,
            "pushNotifications": False,
            "statefulTasks": True,
            "idempotency": True,
            "cancellation": True,
        },
        skills=[
            AgentSkill(
                name="invoice_action_agent",
                description="Autonomous invoice decision agent that analyzes claim packages, selects evidence-based business actions, and executes receipts safely upon approval.",
                tags=["invoicing", "finance", "compliance", "a2a", "evidence-reasoning"],
            )
        ],
        supportedInterfaces=[
            SupportedInterface(
                url=interface_url,
                protocolBinding="HTTP+JSON",
                protocolVersion="1.0",
            )
        ],
        defaultInputModes=[
            "application/vnd.ga5.invoice-claim-batch+json"
        ],
        defaultOutputModes=[
            "application/vnd.ga5.invoice-action-proposals+json",
            "application/vnd.ga5.invoice-action-receipts+json",
        ],
    )
    return JSONResponse(
        content=card.model_dump(),
        media_type="application/a2a+json",
    )
