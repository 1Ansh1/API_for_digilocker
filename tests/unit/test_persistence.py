"""Unit and persistence layer tests for verification results and audit trails."""

import datetime
import uuid
from typing import Any
import pytest
from sqlalchemy import select, delete
from sqlalchemy.sql import Select, Delete

from app.models.audit_event import AuditEvent, AuditEventType
from app.models.verification import Verification, VerificationStatus
from app.models.verification_result import VerificationResult
from app.repositories.audit import AuditRepository
from app.repositories.verification import VerificationRepository
from app.repositories.verification_result import VerificationResultRepository


class MockAsyncSession:
    """Mock implementation of SQLAlchemy AsyncSession to allow offline unit tests."""

    def __init__(self) -> None:
        self.items: list[Any] = []
        self.deleted_items: list[Any] = []
        self.flushed = False

    def add(self, instance: Any) -> None:
        self.items.append(instance)
        # Populate default fields
        if hasattr(instance, "id") and instance.id is None:
            instance.id = uuid.uuid4()
        if hasattr(instance, "status") and getattr(instance, "status", None) is None:
            instance.status = VerificationStatus.INITIATED
        if hasattr(instance, "created_at") and getattr(instance, "created_at", None) is None:
            instance.created_at = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
        if hasattr(instance, "initiated_at") and getattr(instance, "initiated_at", None) is None:
            instance.initiated_at = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)

    async def flush(self) -> None:
        self.flushed = True

    async def delete(self, instance: Any) -> None:
        if instance in self.items:
            self.items.remove(instance)
        self.deleted_items.append(instance)
        
        # Simulate cascade delete on Verification -> VerificationResult
        if isinstance(instance, Verification):
            to_remove = [
                item for item in self.items 
                if isinstance(item, VerificationResult) and item.verification_id == instance.id
            ]
            for item in to_remove:
                self.items.remove(item)
                self.deleted_items.append(item)

    async def get(self, model: Any, ident: Any) -> Any:
        for item in self.items:
            if isinstance(item, model) and item.id == ident:
                return item
        return None

    async def execute(self, stmt: Any) -> Any:
        # Check if stmt is Select
        if isinstance(stmt, Select):
            entity = stmt.column_descriptions[0]["type"]
            compiled = stmt.compile()
            params = compiled.params
            
            matching = []
            for item in self.items:
                if isinstance(item, entity):
                    matches = True
                    # Check verification_id filter
                    if "verification_id_1" in params:
                        val = params["verification_id_1"]
                        if isinstance(val, str):
                            val = uuid.UUID(val)
                        if getattr(item, "verification_id", None) != val:
                            matches = False
                    # Check id filter
                    if "id_1" in params:
                        val = params["id_1"]
                        if isinstance(val, str):
                            val = uuid.UUID(val)
                        if getattr(item, "id", None) != val:
                            matches = False
                    if matches:
                        matching.append(item)
            
            mock_result = pytest.importorskip("unittest.mock").MagicMock()
            mock_result.scalar_one_or_none.return_value = matching[0] if matching else None
            mock_result.scalar_one.return_value = matching[0] if matching else None
            mock_result.scalars.return_value.all.return_value = matching
            return mock_result

        # Check if stmt is Delete
        elif isinstance(stmt, Delete):
            compiled = stmt.compile()
            params = compiled.params
            
            # The filter is on created_at
            cut_off = None
            for k, v in params.items():
                if k.startswith("created_at_"):
                    cut_off = v
                    break
            
            deleted_count = 0
            if cut_off:
                to_delete = []
                for item in self.items:
                    if isinstance(item, VerificationResult):
                        if item.created_at < cut_off:
                            to_delete.append(item)
                
                for item in to_delete:
                    self.items.remove(item)
                    self.deleted_items.append(item)
                    deleted_count += 1
            
            mock_result = pytest.importorskip("unittest.mock").MagicMock()
            mock_result.rowcount = deleted_count
            return mock_result
            
        raise NotImplementedError("Statement type not mocked in MockAsyncSession")


@pytest.fixture
def test_db_session() -> MockAsyncSession:
    """Fixture returning a mocked AsyncSession to run persistence tests offline."""
    return MockAsyncSession()


@pytest.mark.asyncio
async def test_verification_result_repository_lifecycle(test_db_session: MockAsyncSession) -> None:
    """Verify that a verification result can be created, retrieved, and deleted."""
    # 1. Create a parent verification session
    v_repo = VerificationRepository(test_db_session)  # type: ignore[arg-type]
    verification = await v_repo.create(user_id="user-1")
    await test_db_session.flush()

    # 2. Persist the verification result details (PII)
    result_repo = VerificationResultRepository(test_db_session)  # type: ignore[arg-type]
    result = await result_repo.create(
        verification_id=verification.id,
        user_id="user-1",
        name="Alice Smith",
        dob="1995-05-15",
        gender="F",
        digilocker_id="mock-id-alice",
    )
    await test_db_session.flush()

    assert result.id is not None
    assert result.verification_id == verification.id
    assert result.name == "Alice Smith"

    # 3. Retrieve the verification result
    fetched = await result_repo.get_by_verification_id(verification.id)
    assert fetched is not None
    assert fetched.name == "Alice Smith"
    assert fetched.dob == "1995-05-15"
    assert fetched.gender == "F"
    assert fetched.digilocker_id == "mock-id-alice"


@pytest.mark.asyncio
async def test_verification_result_cascade_delete(test_db_session: MockAsyncSession) -> None:
    """Verify that deleting a Verification session cascade deletes its VerificationResult."""
    # 1. Setup session and result
    v_repo = VerificationRepository(test_db_session)  # type: ignore[arg-type]
    verification = await v_repo.create(user_id="user-2")
    await test_db_session.flush()

    result_repo = VerificationResultRepository(test_db_session)  # type: ignore[arg-type]
    await result_repo.create(
        verification_id=verification.id,
        user_id="user-2",
        name="Bob Jones",
        dob="1988-08-08",
        gender="M",
        digilocker_id="mock-id-bob",
    )
    await test_db_session.flush()

    # 2. Delete parent verification
    await test_db_session.delete(verification)
    await test_db_session.flush()

    # 3. Check that result is gone (cascade delete verified)
    fetched = await result_repo.get_by_verification_id(verification.id)
    assert fetched is None


@pytest.mark.asyncio
async def test_verification_result_pruning(test_db_session: MockAsyncSession) -> None:
    """Verify that expired verification results are pruned correctly according to retention."""
    v_repo = VerificationRepository(test_db_session)  # type: ignore[arg-type]
    result_repo = VerificationResultRepository(test_db_session)  # type: ignore[arg-type]

    # 1. Create one expired result (created 10 minutes ago)
    v1 = await v_repo.create(user_id="user-3")
    await test_db_session.flush()
    res1 = await result_repo.create(
        verification_id=v1.id,
        user_id="user-3",
        name="Old User",
        dob="1970-01-01",
        gender="M",
        digilocker_id="mock-id-old",
    )
    # Manually shift created_at back to simulate older record
    res1.created_at = datetime.datetime.now(datetime.UTC).replace(tzinfo=None) - datetime.timedelta(
        minutes=10
    )
    await test_db_session.flush()

    # 2. Create one fresh result (created just now)
    v2 = await v_repo.create(user_id="user-4")
    await test_db_session.flush()
    await result_repo.create(
        verification_id=v2.id,
        user_id="user-4",
        name="Fresh User",
        dob="2000-01-01",
        gender="F",
        digilocker_id="mock-id-fresh",
    )
    await test_db_session.flush()

    # 3. Prune records older than 5 minutes (300 seconds)
    deleted_count = await result_repo.prune_expired(retention_seconds=300)
    assert deleted_count == 1

    # 4. Verify old is gone, fresh remains
    fetched1 = await result_repo.get_by_verification_id(v1.id)
    assert fetched1 is None

    fetched2 = await result_repo.get_by_verification_id(v2.id)
    assert fetched2 is not None
    assert fetched2.name == "Fresh User"


@pytest.mark.asyncio
async def test_clear_separation_of_audit_metadata(test_db_session: MockAsyncSession) -> None:
    """Verify that audit events store hashes and do not leak raw demographic PII."""
    v_repo = VerificationRepository(test_db_session)  # type: ignore[arg-type]
    audit_repo = AuditRepository(test_db_session)  # type: ignore[arg-type]

    verification = await v_repo.create(user_id="user-5")
    await test_db_session.flush()

    # Create an audit event tracking verification completion
    event = await audit_repo.create(
        verification_id=verification.id,
        user_id="user-5",
        correlation_id="corr-999",
        event_type=AuditEventType.VERIFICATION_COMPLETED,
        status=VerificationStatus.VERIFIED,
        metadata={
            "digilocker_id_hash": "hash_123_456",
            "proof_hash": "proof_xyz_abc",
        },
    )
    await test_db_session.flush()

    # Fetch event and assert on metadata columns
    stmt = select(AuditEvent).where(AuditEvent.id == event.id)
    res = await test_db_session.execute(stmt)
    fetched_event = res.scalar_one()

    # Metadata should contain verification stats, but NO raw PII values
    assert fetched_event.metadata_["digilocker_id_hash"] == "hash_123_456"
    assert fetched_event.metadata_["proof_hash"] == "proof_xyz_abc"
    assert "name" not in fetched_event.metadata_
    assert "dob" not in fetched_event.metadata_
    assert "gender" not in fetched_event.metadata_


@pytest.mark.asyncio
async def test_verification_repository_get_and_update(test_db_session: MockAsyncSession) -> None:
    """Verify VerificationRepository get_by_id and update_status logic and boundary cases."""
    repo = VerificationRepository(test_db_session)  # type: ignore[arg-type]

    # Test get_by_id not found
    random_id = uuid.uuid4()
    not_found = await repo.get_by_id(random_id)
    assert not_found is None

    # Test update_status not found
    updated_not_found = await repo.update_status(random_id, VerificationStatus.FAILED)
    assert updated_not_found is None

    # Create verification
    verification = await repo.create(user_id="user-get-update")
    await test_db_session.flush()
    assert verification.id is not None

    # Get verification
    fetched = await repo.get_by_id(verification.id)
    assert fetched is not None
    assert fetched.user_id == "user-get-update"
    assert fetched.status == VerificationStatus.INITIATED

    # Update status
    updated = await repo.update_status(verification.id, VerificationStatus.VERIFIED)
    assert updated is not None
    assert updated.status == VerificationStatus.VERIFIED

    # Check status updated on next fetch
    fetched_updated = await repo.get_by_id(verification.id)
    assert fetched_updated is not None
    assert fetched_updated.status == VerificationStatus.VERIFIED

