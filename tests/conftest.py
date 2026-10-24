import pytest
from typing import Generator
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker, Session

from app.main import app
from app.database import Base, get_db
from app.models.entities import TaskModel, IdempotencyModel, ProposalModel, PackageDecisionCacheModel

# In-memory SQLite using StaticPool so all connections share the same memory DB
test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

@event.listens_for(test_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

# Create tables once for the test run
Base.metadata.create_all(bind=test_engine)


@pytest.fixture(scope="function")
def db_session() -> Generator[Session, None, None]:
    session = TestingSessionLocal()
    try:
        # Clear data from previous tests
        session.query(IdempotencyModel).delete()
        session.query(ProposalModel).delete()
        session.query(TaskModel).delete()
        session.query(PackageDecisionCacheModel).delete()
        session.commit()
        yield session
    finally:
        session.close()


@pytest.fixture(scope="function")
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def override_get_db():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers():
    return {
        "Authorization": "Bearer test-secret-token-12345",
        "A2A-Version": "1.0",
        "Content-Type": "application/a2a+json",
    }


@pytest.fixture
def sample_claim_batch_payload():
    """Build a realistic claim batch of 12 invoice packages with decisive evidence paragraphs and decoys."""
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
        pkg_id = f"pkg_{i+1:02d}"
        packages.append({
            "packageId": pkg_id,
            "vendorName": f"Acme Vendor {i+1} Pvt Ltd",
            "invoiceNumber": f"INV-2026-{1000 + i}",
            "amountMinor": (i + 1) * 25000,
            "currency": "INR",
            "documentText": (
                "COVER SHEET: Reference [COVER-001]. For historical records only.\n\n"
                f"ACTION PARAGRAPH: This invoice is {decisive_text}. Authoritative verification {ref1} confirms terms. "
                f"Operational record {ref2} and compliance mandate {ref3} apply directly.\n\n"
                "ARCHIVE EXAMPLE: Training decoy [DECOY-999] was resolved in prior audit period."
            )
        })

    return {
        "message": {
            "messageId": "msg_initial_test_001",
            "role": "ROLE_USER",
            "parts": [
                {
                    "mediaType": "application/vnd.ga5.invoice-claim-batch+json",
                    "data": {
                        "batchId": "batch_test_alpha_01",
                        "policyRevision": "rev_2026_q4",
                        "packages": packages,
                    }
                }
            ]
        },
        "configuration": {
            "returnImmediately": False,
            "historyLength": 20,
            "acceptedOutputModes": [
                "application/vnd.ga5.invoice-action-proposals+json",
                "application/vnd.ga5.invoice-action-receipts+json"
            ]
        }
    }
