from typing import List, Literal
from pydantic import BaseModel, Field

InvoiceActionType = Literal[
    "settle_invoice",
    "request_approval",
    "hold_invoice",
    "reject_duplicate",
    "open_exception",
]

OutcomeType = Literal["ACCEPTED", "REJECTED"]


class InvoiceFacts(BaseModel):
    vendorName: str
    invoiceNumber: str
    amountMinor: int
    currency: str = "INR"


class InvoiceProposal(BaseModel):
    packageId: str
    actionId: str = Field(..., min_length=12, description="Durable unique id (at least 12 characters)")
    action: InvoiceActionType
    facts: InvoiceFacts
    evidenceRefs: List[str] = Field(..., min_length=3, max_length=3, description="Exactly three decisive references from the documents")
    rationale: str = Field(..., min_length=60, max_length=1500, description="60-1500 chars; names action and cites evidence")


class InvoiceProposalsData(BaseModel):
    batchId: str
    proposals: List[InvoiceProposal]


class ContinuationResult(BaseModel):
    packageId: str
    actionId: str
    action: InvoiceActionType
    outcome: OutcomeType
    receiptNonce: str


class ContinuationResultsData(BaseModel):
    batchId: str
    results: List[ContinuationResult]


class ExecutionReceipt(BaseModel):
    packageId: str
    actionId: str
    action: InvoiceActionType
    receiptNonce: str
    facts: InvoiceFacts
    evidenceRefs: List[str] = Field(..., min_length=3, max_length=3, description="Exactly three decisive references from the documents")


class InvoiceReceiptsData(BaseModel):
    batchId: str
    executions: List[ExecutionReceipt]
