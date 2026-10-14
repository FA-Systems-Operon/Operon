"""Endpoints for creating and looking up clients."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.db import get_db
from src.models import Client
from src.schemas import ClientIn, ClientOut

router = APIRouter(prefix="/clients", tags=["clients"])

DbSession = Annotated[Session, Depends(get_db)]


@router.post("", response_model=ClientOut, status_code=status.HTTP_201_CREATED)
def create_client(body: ClientIn, db: DbSession) -> Client:
    """Create a new client."""
    client = Client(name=body.name)
    db.add(client)
    db.commit()
    db.refresh(client)  # loads id and created_at filled in by Postgres
    return client


@router.get("/{client_id}", response_model=ClientOut)
def get_client(client_id: uuid.UUID, db: DbSession) -> Client:
    """Return a client by ID."""
    client = db.get(Client, client_id)
    if client is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")
    return client
