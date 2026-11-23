"""Unit tests for Organization and Membership Pydantic schemas."""

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from iryx.auth.models import Membership, MembershipRole, Organization
from iryx.auth.schemas import (
    MembershipCreate,
    MembershipResponse,
    OrganizationCreate,
    OrganizationResponse,
)


def test_organization_create_nominal() -> None:
    """Verify OrganizationCreate accepts valid name and strips whitespace."""
    schema = OrganizationCreate(name="  CERT Interne  ")
    assert schema.name == "CERT Interne"


def test_organization_create_rejects_empty_name() -> None:
    """Verify OrganizationCreate rejects empty name."""
    with pytest.raises(ValidationError) as exc_info:
        OrganizationCreate(name="")
    assert any(err["loc"] == ("name",) for err in exc_info.value.errors())


def test_organization_create_rejects_whitespace_only_name() -> None:
    """Verify OrganizationCreate rejects whitespace-only name."""
    with pytest.raises(ValidationError) as exc_info:
        OrganizationCreate(name="    ")
    assert any(err["loc"] == ("name",) for err in exc_info.value.errors())


def test_organization_create_rejects_name_exceeding_max_length() -> None:
    """Verify OrganizationCreate rejects name longer than 255 chars."""
    with pytest.raises(ValidationError) as exc_info:
        OrganizationCreate(name="A" * 256)
    assert any(err["loc"] == ("name",) for err in exc_info.value.errors())


def test_organization_create_rejects_missing_name() -> None:
    """Verify OrganizationCreate rejects missing name."""
    with pytest.raises(ValidationError) as exc_info:
        OrganizationCreate.model_validate({})
    assert any(err["loc"] == ("name",) for err in exc_info.value.errors())


def test_organization_response_serialization() -> None:
    """Verify OrganizationResponse serializes fields accurately to dict and JSON."""
    now = datetime.now(UTC)
    org_id = uuid.uuid4()

    response = OrganizationResponse(
        id=org_id,
        name="SOC IRYX",
        created_at=now,
        updated_at=now,
    )

    dumped = response.model_dump()
    assert dumped["id"] == org_id
    assert dumped["name"] == "SOC IRYX"
    assert dumped["created_at"] == now

    json_str = response.model_dump_json()
    assert str(org_id) in json_str
    assert "SOC IRYX" in json_str


def test_organization_response_from_orm() -> None:
    """Verify OrganizationResponse instantiates from Organization ORM model."""
    now = datetime.now(UTC)
    org_id = uuid.uuid4()

    org_orm = Organization(
        id=org_id,
        name="Digital Forensics Lab",
        created_at=now,
        updated_at=now,
    )

    response = OrganizationResponse.model_validate(org_orm)
    assert response.id == org_id
    assert response.name == "Digital Forensics Lab"
    assert response.created_at == now
    assert response.updated_at == now


def test_membership_role_enum_values() -> None:
    """Verify MembershipRole has strictly the 4 expected roles and string semantics."""
    assert MembershipRole.ADMIN == "admin"
    assert MembershipRole.ANALYST == "analyst"
    assert MembershipRole.INVESTIGATOR == "investigator"
    assert MembershipRole.VIEWER == "viewer"
    assert len(MembershipRole) == 4


def test_membership_create_nominal() -> None:
    """Verify MembershipCreate accepts all 4 valid roles (both enum and str)."""
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()

    for role_val in ["admin", "analyst", "investigator", "viewer"]:
        schema = MembershipCreate(
            organization_id=org_id,
            user_id=user_id,
            role=role_val,  # type: ignore[arg-type]
        )
        assert schema.organization_id == org_id
        assert schema.user_id == user_id
        assert schema.role == role_val


def test_membership_create_rejects_invalid_role() -> None:
    """Verify MembershipCreate rejects unauthorized roles like superuser, editor, owner."""
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()

    for invalid_role in ["superuser", "editor", "root", "owner", "", "admin_user"]:
        with pytest.raises(ValidationError) as exc_info:
            MembershipCreate(
                organization_id=org_id,
                user_id=user_id,
                role=invalid_role,  # type: ignore[arg-type]
            )
        assert any(err["loc"] == ("role",) for err in exc_info.value.errors())


def test_membership_create_rejects_invalid_uuid() -> None:
    """Verify MembershipCreate rejects malformed UUID fields."""
    with pytest.raises(ValidationError) as exc_info:
        MembershipCreate(
            organization_id="not-a-uuid",  # type: ignore[arg-type]
            user_id=uuid.uuid4(),
            role=MembershipRole.ANALYST,
        )
    assert any(err["loc"] == ("organization_id",) for err in exc_info.value.errors())


def test_membership_create_rejects_missing_fields() -> None:
    """Verify MembershipCreate rejects payloads missing required fields."""
    valid_data = {
        "organization_id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "role": MembershipRole.ANALYST,
    }

    # Missing organization_id
    data_no_org = {k: v for k, v in valid_data.items() if k != "organization_id"}
    with pytest.raises(ValidationError) as exc_info:
        MembershipCreate.model_validate(data_no_org)
    assert any(err["loc"] == ("organization_id",) for err in exc_info.value.errors())

    # Missing user_id
    data_no_user = {k: v for k, v in valid_data.items() if k != "user_id"}
    with pytest.raises(ValidationError) as exc_info:
        MembershipCreate.model_validate(data_no_user)
    assert any(err["loc"] == ("user_id",) for err in exc_info.value.errors())

    # Missing role
    data_no_role = {k: v for k, v in valid_data.items() if k != "role"}
    with pytest.raises(ValidationError) as exc_info:
        MembershipCreate.model_validate(data_no_role)
    assert any(err["loc"] == ("role",) for err in exc_info.value.errors())


def test_membership_response_serialization() -> None:
    """Verify MembershipResponse serializes accurately to dict and JSON."""
    now = datetime.now(UTC)
    m_id = uuid.uuid4()
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()

    response = MembershipResponse(
        id=m_id,
        organization_id=org_id,
        user_id=user_id,
        role=MembershipRole.INVESTIGATOR,
        created_at=now,
    )

    dumped = response.model_dump()
    assert dumped["id"] == m_id
    assert dumped["organization_id"] == org_id
    assert dumped["user_id"] == user_id
    assert dumped["role"] == MembershipRole.INVESTIGATOR

    dumped_json = response.model_dump_json()
    assert str(m_id) in dumped_json
    assert "investigator" in dumped_json


def test_membership_response_from_orm() -> None:
    """Verify MembershipResponse instantiates from Membership ORM model."""
    now = datetime.now(UTC)
    m_id = uuid.uuid4()
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()

    membership_orm = Membership(
        id=m_id,
        organization_id=org_id,
        user_id=user_id,
        role="viewer",
        created_at=now,
    )

    response = MembershipResponse.model_validate(membership_orm)
    assert response.id == m_id
    assert response.organization_id == org_id
    assert response.user_id == user_id
    assert response.role == MembershipRole.VIEWER
    assert response.created_at == now
