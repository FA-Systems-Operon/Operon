"""Unit tests for the transactional version numbering service."""

from src.models import (
    Client,
    ClientProfile,
    ClientProfileVersion,
    Playbook,
    PlaybookVersion,
)
from src.versioning import next_client_profile_version, next_playbook_version

# --- next_client_profile_version ---


def test_next_client_profile_version_no_existing(db_session):
    client = Client(name="Test Client")
    db_session.add(client)
    db_session.flush()

    profile = ClientProfile(client_id=client.id)
    db_session.add(profile)
    db_session.flush()

    assert next_client_profile_version(db_session, profile.id) == 1


def test_next_client_profile_version_with_existing(db_session):
    client = Client(name="Test Client")
    db_session.add(client)
    db_session.flush()

    profile = ClientProfile(client_id=client.id)
    db_session.add(profile)
    db_session.flush()

    db_session.add(
        ClientProfileVersion(client_profile_id=profile.id, version_number=1, data={})
    )
    db_session.add(
        ClientProfileVersion(client_profile_id=profile.id, version_number=2, data={})
    )
    db_session.commit()

    assert next_client_profile_version(db_session, profile.id) == 3


def test_next_client_profile_version_isolated_per_profile(db_session):
    client = Client(name="Test Client")
    db_session.add(client)
    db_session.flush()

    profile_a = ClientProfile(client_id=client.id)
    profile_b = ClientProfile(client_id=client.id)
    db_session.add_all([profile_a, profile_b])
    db_session.flush()

    db_session.add(
        ClientProfileVersion(client_profile_id=profile_a.id, version_number=1, data={})
    )
    db_session.add(
        ClientProfileVersion(client_profile_id=profile_a.id, version_number=2, data={})
    )
    db_session.commit()

    # profile_b has no versions yet — should start at 1 regardless of profile_a
    assert next_client_profile_version(db_session, profile_b.id) == 1


# --- next_playbook_version ---


def test_next_playbook_version_no_existing(db_session):
    playbook = Playbook()
    db_session.add(playbook)
    db_session.flush()

    assert next_playbook_version(db_session, playbook.id) == 1


def test_next_playbook_version_with_existing(db_session):
    playbook = Playbook()
    db_session.add(playbook)
    db_session.flush()

    db_session.add(PlaybookVersion(playbook_id=playbook.id, version_number=1, data={}))
    db_session.add(PlaybookVersion(playbook_id=playbook.id, version_number=2, data={}))
    db_session.commit()

    assert next_playbook_version(db_session, playbook.id) == 3


def test_next_playbook_version_isolated_per_playbook(db_session):
    playbook_a = Playbook()
    playbook_b = Playbook()
    db_session.add_all([playbook_a, playbook_b])
    db_session.flush()

    db_session.add(
        PlaybookVersion(playbook_id=playbook_a.id, version_number=1, data={})
    )
    db_session.commit()

    assert next_playbook_version(db_session, playbook_b.id) == 1
