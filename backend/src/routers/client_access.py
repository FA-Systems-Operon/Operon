"""Admin endpoints for assigning users to clients (#148)."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert

from src.audit import AuditAction, record_audit_event
from src.auth import DbSession, require_role
from src.models import Client, ClientAccess, Role, User
from src.routers.auth import UserOut
from src.schemas import ClientOut

router = APIRouter(prefix="/api/v1/users", tags=["client access"])
AdminUser = Annotated[User, Depends(require_role(Role.ADMIN))]


class ClientAccessOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID
    client_id: uuid.UUID
    created_at: datetime


@router.get("", response_model=list[UserOut])
def list_access_users(db: DbSession, _admin: AdminUser) -> list[User]:
    """List users for the admin's client-assignment screen."""
    return list(db.scalars(select(User).order_by(User.email, User.id)))


@router.get("/{user_id}/clients", response_model=list[ClientOut])
def list_user_clients(
    user_id: uuid.UUID, db: DbSession, _admin: AdminUser
) -> list[Client]:
    """List a user's explicit assignments, including an empty list."""
    if db.get(User, user_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    query = (
        select(Client)
        .join(ClientAccess, ClientAccess.client_id == Client.id)
        .where(ClientAccess.user_id == user_id)
        .order_by(func.lower(Client.name), Client.id)
    )
    return list(db.scalars(query))


@router.put("/{user_id}/clients/{client_id}", response_model=ClientAccessOut)
def grant_client_access(
    user_id: uuid.UUID, client_id: uuid.UUID, db: DbSession, admin: AdminUser
) -> ClientAccess:
    """Grant access, returning the existing assignment when already granted."""
    if db.get(User, user_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if db.get(Client, client_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")

    try:
        granted = db.execute(
            insert(ClientAccess)
            .values(user_id=user_id, client_id=client_id)
            .on_conflict_do_nothing(
                index_elements=[ClientAccess.user_id, ClientAccess.client_id]
            )
            .returning(ClientAccess.user_id)
        ).scalar_one_or_none()
        if granted is not None:
            record_audit_event(
                db,
                actor_id=admin.id,
                action=AuditAction.CLIENT_ACCESS_GRANTED,
                object_type="client",
                object_id=client_id,
                target_user_id=user_id,
            )
        assignment = db.get(ClientAccess, (user_id, client_id))
        db.commit()
        db.refresh(assignment)
    except Exception:
        db.rollback()
        raise
    return assignment


@router.delete("/{user_id}/clients/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_client_access(
    user_id: uuid.UUID, client_id: uuid.UUID, db: DbSession, admin: AdminUser
) -> None:
    """Revoke an assignment. Repeated revokes succeed for existing users and clients."""
    if db.get(User, user_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if db.get(Client, client_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")

    try:
        revoked = db.execute(
            delete(ClientAccess)
            .where(ClientAccess.user_id == user_id, ClientAccess.client_id == client_id)
            .returning(ClientAccess.user_id)
        ).scalar_one_or_none()
        if revoked is not None:
            record_audit_event(
                db,
                actor_id=admin.id,
                action=AuditAction.CLIENT_ACCESS_REVOKED,
                object_type="client",
                object_id=client_id,
                target_user_id=user_id,
            )
        db.commit()
    except Exception:
        db.rollback()
        raise
