"""AT 3.3 (#49): pinned source pair -> generated flags -> persisted draft.

Shared synthetic cases are also rendered by DraftFlags.acceptance.test.tsx.
Fake model output tests the contract and workflow, not semantic model accuracy.
"""

import copy
import json
import os
from pathlib import Path

import pytest
from sqlalchemy import func, select
from tests.test_onboarding_jobs import SourceAwareProvider, get_job, start, upload_pair

from src.models import ClientProfileVersion

CASES = json.loads(
    (Path(__file__).parent / "fixtures/onboarding_flags/cases.json").read_text()
)


def bind_documents(reply, ids):
    payload = copy.deepcopy(reply)
    for reference in payload["source_references"]:
        reference["document_id"] = ids[reference["document_id"]]
    for conflict in payload["conflicts"]:
        for alternative in conflict["alternatives"]:
            alternative["document_id"] = ids[alternative["document_id"]]
    return payload


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_generated_flags_survive_job_persistence_and_retrieval(
    client,
    db_session,
    demo_client,
    profile_factory,
    monkeypatch,
    case,
):
    original = profile_factory(approved=True, data={"email": "approved@example.test"})
    provider = SourceAwareProvider(lambda ids: bind_documents(case["reply"], ids))
    monkeypatch.setattr("src.onboarding_jobs.get_provider", lambda: provider)
    transcript, intake = upload_pair(client, demo_client, **case["documents"])
    response = start(client, demo_client, transcript, intake)
    assert response.status_code == 201, response.text
    job = get_job(client, demo_client, response.json())
    assert job["status"] == "succeeded", job
    assert len(provider.prompts) == 1

    url = f"/client-profiles/{original.client_profile_id}"
    versions = client.get(f"{url}/versions").json()
    saved = next(
        version for version in versions if version["id"] == job["result_version_id"]
    )
    data = saved["data"]
    assert saved["status"] == "draft" and saved["version_number"] == 2
    assert data["assessment"] == {
        "rules_version": 1,
        "missing_fields": case["expected"]["missing_fields"],
    }
    assert [conflict["field"] for conflict in data["conflicts"]] == case["expected"][
        "conflict_fields"
    ]
    expected_reply = bind_documents(
        case["reply"], {"transcript": transcript["id"], "intake": intake["id"]}
    )
    assert {key: data[key] for key in expected_reply} == expected_reply
    if case["expected"]["conflict_fields"]:
        assert data["email"] is None
        alternatives = data["conflicts"][0]["alternatives"]
        assert [alternative["value"] for alternative in alternatives] == case[
            "expected"
        ]["email_values"]
        assert {alternative["document_id"] for alternative in alternatives} == {
            transcript["id"],
            intake["id"],
        }
    assert client.get(f"{url}/latest-approved").json()["id"] == str(original.id)
    assert versions[0]["data"] == {"email": "approved@example.test"}


def test_invalid_conflict_fails_job_without_persisting_a_draft(
    client,
    db_session,
    demo_client,
    monkeypatch,
):
    case = CASES[0]

    def invalid_reply(ids):
        payload = bind_documents(case["reply"], ids)
        payload["conflicts"][0]["alternatives"][1]["quote"] = "Invented evidence"
        return payload

    monkeypatch.setattr(
        "src.onboarding_jobs.get_provider", lambda: SourceAwareProvider(invalid_reply)
    )
    transcript, intake = upload_pair(client, demo_client, **case["documents"])
    response = start(client, demo_client, transcript, intake)
    job = get_job(client, demo_client, response.json())
    assert job["status"] == "failed"
    assert job["result_version_id"] is None
    assert (
        db_session.scalar(select(func.count()).select_from(ClientProfileVersion)) == 0
    )


@pytest.mark.skipif(
    os.getenv("RUN_OLLAMA_TESTS") != "1",
    reason="set RUN_OLLAMA_TESTS=1 to call local Ollama",
)
@pytest.mark.parametrize(
    "case", [CASES[0], CASES[1], CASES[3]], ids=lambda case: "live_" + case["id"]
)
def test_real_provider_job_saves_validated_flags(  # pragma: no cover
    client,
    db_session,
    demo_client,
    profile_factory,
    case,
):
    """Real inference, UUID sources and persistence; CI has no local model."""
    original = profile_factory(approved=True, data={"email": "approved@example.test"})
    transcript, intake = upload_pair(client, demo_client, **case["documents"])
    response = start(client, demo_client, transcript, intake)
    assert response.status_code == 201, response.text
    job = get_job(client, demo_client, response.json())
    assert job["status"] == "succeeded", job
    versions = client.get(
        f"/client-profiles/{original.client_profile_id}/versions"
    ).json()
    saved = next(
        version for version in versions if version["id"] == job["result_version_id"]
    )
    assert saved["status"] == "draft"
    data = saved["data"]
    assert data["assessment"]["missing_fields"] == case["expected"]["missing_fields"]
    assert [conflict["field"] for conflict in data["conflicts"]] == case["expected"][
        "conflict_fields"
    ]
    if data["conflicts"]:
        assert data["email"] is None
        alternatives = data["conflicts"][0]["alternatives"]
        assert sorted(value["value"] for value in alternatives) == sorted(
            case["expected"]["email_values"]
        )
        assert {value["document_id"] for value in alternatives} == {
            transcript["id"],
            intake["id"],
        }
    assert versions[0]["data"] == {"email": "approved@example.test"}
