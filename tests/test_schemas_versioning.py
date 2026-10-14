"""Unit tests for the versioning schemas: ClientProfileVersionOut and PlaybookVersionOut.

These tests are self-contained — no database or HTTP client needed.
"""

import uuid
from datetime import datetime, timezone

import pytest

from src.schemas import (
    ClientProfileOut,
    ClientProfileVersionOut,
    PlaybookOut,
    PlaybookVersionOut,
)

NOW = datetime.now(timezone.utc)


# --- ClientProfileOut ---


def test_client_profile_out_valid():
    profile = ClientProfileOut(
        id=uuid.uuid4(),
        client_id=uuid.uuid4(),
        created_at=NOW,
    )

    assert isinstance(profile.id, uuid.UUID)
    assert isinstance(profile.client_id, uuid.UUID)
    assert profile.created_at == NOW


def test_client_profile_out_missing_field():
    with pytest.raises(Exception):
        ClientProfileOut(id=uuid.uuid4(), created_at=NOW)


# --- ClientProfileVersionOut ---


def test_client_profile_version_out_valid():
    version = ClientProfileVersionOut(
        id=uuid.uuid4(),
        client_profile_id=uuid.uuid4(),
        version_number=1,
        data={"key": "value"},
        created_at=NOW,
    )

    assert version.version_number == 1
    assert version.data == {"key": "value"}


def test_client_profile_version_out_empty_data():
    version = ClientProfileVersionOut(
        id=uuid.uuid4(),
        client_profile_id=uuid.uuid4(),
        version_number=1,
        data={},
        created_at=NOW,
    )

    assert version.data == {}


def test_client_profile_version_out_missing_version_number():
    with pytest.raises(Exception):
        ClientProfileVersionOut(
            id=uuid.uuid4(),
            client_profile_id=uuid.uuid4(),
            data={},
            created_at=NOW,
        )


@pytest.mark.parametrize("version_number", [1, 2, 100])
def test_client_profile_version_number_values(version_number: int):
    version = ClientProfileVersionOut(
        id=uuid.uuid4(),
        client_profile_id=uuid.uuid4(),
        version_number=version_number,
        data={},
        created_at=NOW,
    )

    assert version.version_number == version_number


# --- PlaybookOut ---


def test_playbook_out_valid():
    playbook = PlaybookOut(
        id=uuid.uuid4(),
        created_at=NOW,
    )

    assert isinstance(playbook.id, uuid.UUID)
    assert playbook.created_at == NOW


def test_playbook_out_missing_field():
    with pytest.raises(Exception):
        PlaybookOut(created_at=NOW)


# --- PlaybookVersionOut ---


def test_playbook_version_out_valid():
    version = PlaybookVersionOut(
        id=uuid.uuid4(),
        playbook_id=uuid.uuid4(),
        version_number=1,
        data={"steps": ["step1", "step2"]},
        created_at=NOW,
    )

    assert version.version_number == 1
    assert version.data == {"steps": ["step1", "step2"]}


def test_playbook_version_out_empty_data():
    version = PlaybookVersionOut(
        id=uuid.uuid4(),
        playbook_id=uuid.uuid4(),
        version_number=1,
        data={},
        created_at=NOW,
    )

    assert version.data == {}


def test_playbook_version_out_missing_version_number():
    with pytest.raises(Exception):
        PlaybookVersionOut(
            id=uuid.uuid4(),
            playbook_id=uuid.uuid4(),
            data={},
            created_at=NOW,
        )


@pytest.mark.parametrize("version_number", [1, 2, 100])
def test_playbook_version_number_values(version_number: int):
    version = PlaybookVersionOut(
        id=uuid.uuid4(),
        playbook_id=uuid.uuid4(),
        version_number=version_number,
        data={},
        created_at=NOW,
    )

    assert version.version_number == version_number