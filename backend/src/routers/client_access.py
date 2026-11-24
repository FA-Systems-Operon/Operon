"""Admin endpoints for assigning users to clients (#148)."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.dialects.postgresql import insert

from src.auth import DbSession, require_role
from src.models import Client, ClientAccess, Role, User

router = APIRouter(prefix="/api/v1/users", tags=["client access"])
AdminUser = Annotated[User, Depends(require_role(Role.ADMIN))]


class ClientAccessOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID
    client_id: uuid.UUID
    created_at: datetime


@router.put("/{user_id}/clients/{client_id}", response_model=ClientAccessOut)
def grant_client_access(
    user_id: uuid.UUID, client_id: uuid.UUID, db: DbSession, _admin: AdminUser
) -> ClientAccess:
    """Grant access, returning the existing assignment when already granted."""
    if db.get(User, user_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if db.get(Client, client_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")

    try:
        db.execute(
            insert(ClientAccess)
            .values(user_id=user_id, client_id=client_id)
            .on_conflict_do_nothing(
                index_elements=[ClientAccess.user_id, ClientAccess.client_id]
            )
        )
        assignment = db.get(ClientAccess, (user_id, client_id))
        db.commit()
        db.refresh(assignment)
    except Exception:
        db.rollback()
        raise
    return assignment
