import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from src.models import (
    Artifact,
    ArtifactVersion,
    ClientProfile,
    ClientProfileVersion,
    ReviewStatus,
)


@pytest.fixture
def profile_version(profile_factory):
    return profile_factory(data={"a": 1})


@pytest.fixture
def artifact_version(db_session, profile_version):
    artifact = Artifact(client_id=profile_version.profile.client_id, kind="brief")
    db_session.add(artifact)
    db_session.flush()
    av = ArtifactVersion(
        artifact_id=artifact.id,
        version_number=1,
        client_profile_version_id=profile_version.id,
    )
    db_session.add(av)
    db_session.commit()
    return av


def test_profile_version_data_cannot_change(db_session, profile_version):
    profile_version.data = {"a": 2}
    with pytest.raises(ValueError, match="immutable"):
        db_session.commit()
    db_session.rollback()


def test_profile_version_number_cannot_change(db_session, profile_version):
    profile_version.version_number = 99
    with pytest.raises(ValueError, match="version_number"):
        db_session.commit()
    db_session.rollback()


def test_playbook_version_data_cannot_change(db_session, playbook_factory):
    version = playbook_factory(data={"a": 1})
    version.data = {"a": 2}
    with pytest.raises(ValueError, match="immutable"):
        db_session.commit()
    db_session.rollback()


def test_review_fields_can_change(db_session, profile_version):
    """status/approved_* are review metadata, not snapshot content."""
    profile_version.status = ReviewStatus.IN_REVIEW
    db_session.commit()
    profile_version.status = ReviewStatus.APPROVED
    profile_version.approved_by = uuid.uuid4()
    profile_version.approved_at = datetime.now(timezone.utc)
    db_session.commit()
    db_session.refresh(profile_version)
    assert profile_version.status == ReviewStatus.APPROVED


def test_approved_at_cannot_be_rewritten(db_session, profile_version):
    profile_version.approved_at = datetime.now(timezone.utc)
    db_session.commit()
    profile_version.approved_at = datetime(2000, 1, 1, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="approved_at"):
        db_session.commit()
    db_session.rollback()


def test_approved_at_cannot_be_cleared(db_session, profile_factory):
    version = profile_factory(approved=True)
    version.approved_at = None
    with pytest.raises(ValueError, match="approved_at"):
        db_session.commit()
    db_session.rollback()


def test_artifact_provenance_link_is_frozen(
    db_session, profile_version, artifact_version
):
    """Repointing an artifact at a newer profile would hide that it's stale."""
    newer = ClientProfileVersion(
        client_profile_id=profile_version.client_profile_id, version_number=2, data={}
    )
    db_session.add(newer)
    db_session.commit()

    artifact_version.client_profile_version_id = newer.id
    with pytest.raises(ValueError, match="client_profile_version_id"):
        db_session.commit()
    db_session.rollback()


def test_artifact_stale_fields_can_change(db_session, artifact_version):
    artifact_version.status = ReviewStatus.STALE
    artifact_version.stale_at = datetime.now(timezone.utc)
    artifact_version.stale_reason = "superseded"
    db_session.commit()  # must not raise


def test_duplicate_version_number_rejected_by_database(db_session, profile_version):
    """The unique constraint is the backstop for concurrent numbering."""
    db_session.add(
        ClientProfileVersion(
            client_profile_id=profile_version.client_profile_id,
            version_number=1,
            data={},
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_same_version_number_allowed_for_different_profiles(
    db_session, profile_version
):
    other = ClientProfile(client_id=profile_version.profile.client_id)
    db_session.add(other)
    db_session.flush()
    db_session.add(
        ClientProfileVersion(client_profile_id=other.id, version_number=1, data={})
    )
    db_session.commit()  # must not raise
