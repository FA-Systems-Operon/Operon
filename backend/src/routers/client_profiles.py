"""Endpoints for creating and versioning client profiles."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.db import get_db
from src.models import ClientProfile, ClientProfileVersion
from src.schemas import ClientProfileOut, ClientProfileVersionOut
from src.versioning import next_client_profile_version

router = APIRouter(prefix="/client-profiles", tags=["client-profiles"])

DbSession = Annotated[Session, Depends(get_db)]


@router.post("", response_model=ClientProfileVersionOut, status_code=status.HTTP_201_CREATED)
def create_client_profile(client_id: uuid.UUID, db: DbSession) -> ClientProfileVersion:
    """Create a new client profile and its first version."""
    profile = ClientProfile(client_id=client_id)
    db.add(profile)
    db.flush()  # assigns profile.id without committing

    version = ClientProfileVersion(
        client_profile_id=profile.id,
        version_number=1,
        data={},
    )
    db.add(version)
    db.commit()
    db.refresh(version)
    return version


@router.put("/{profile_id}", response_model=ClientProfileVersionOut)
def update_client_profile(
    profile_id: uuid.UUID, data: dict, db: DbSession
) -> ClientProfileVersion:
    """Create a new immutable version of a client profile instead of overwriting."""
    profile = db.get(ClientProfile, profile_id)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client profile not found")

    version_number = next_client_profile_version(db, profile_id)
    version = ClientProfileVersion(
        client_profile_id=profile_id,
        version_number=version_number,
        data=data,
    )
    db.add(version)
    db.commit()
    db.refresh(version)
    return version


@router.get("/{profile_id}/versions", response_model=list[ClientProfileVersionOut])
def list_client_profile_versions(
    profile_id: uuid.UUID, db: DbSession
) -> list[ClientProfileVersion]:
    """Return all versions of a client profile, oldest first."""
    profile = db.get(ClientProfile, profile_id)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client profile not found")

    return sorted(profile.versions, key=lambda v: v.version_number)
