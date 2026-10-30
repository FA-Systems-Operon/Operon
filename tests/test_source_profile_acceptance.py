"""AT 3.2 (#48): Given a generated draft profile, when a reviewer opens it, then
every field shows a link to the part of the transcript or intake form it came from.

The model is faked so CI needs no Ollama. Controlled sources are generated, saved
through the #40 API and read back. The reviewer side (each field renders its link)
is frontend/src/components/DraftSourceView.acceptance.test.tsx until #57 exists.
"""

import json

import pytest
from sqlalchemy import func, select
from tests.test_baseline_acceptance import TRANSCRIPTS, FakeProvider

from src.ai.source_prompt import SourceInput, generate_source_profile
from src.models import ClientProfileVersion, ExtractedText, SourceDocument

INTAKE = (
    "Client intake form\n"
    "Contact name: Maya Chen\n"
    "Goal: Launch a customer referral program\n"
    "Goal: 30 qualified bookings per month\n"
)
UNNAMED_CALL = (
    "Discovery call\n\n"
    "Client: Our invoices go out late every month. "
    "We would like invoicing to be automated by spring.\n"
)

# References name their source by kind; the test swaps in the stored document ID.
# "expected" is the independent answer key: which document(s) back each field.
EXAMPLES = {
    "transcript_and_intake": {
        "documents": {
            "transcript": TRANSCRIPTS[0].read_text("utf-8"),
            "intake": INTAKE,
        },
        "draft": {
            "name": "Maya Chen",
            "needs": ["More qualified consultations", "More contact form completions"],
            "goals": ["30 qualified bookings per month", "Launch a referral program"],
            "source_references": [
                ("name", "intake", "Contact name: Maya Chen"),
                ("needs/0", "transcript", "booking more qualified consultations"),
                ("needs/1", "transcript", "few people complete our contact form"),
                ("goals/0", "transcript", "from 15 to 30 per month"),
                ("goals/0", "intake", "Goal: 30 qualified bookings per month"),
                ("goals/1", "intake", "Goal: Launch a customer referral program"),
            ],
        },
        "expected": {
            "name": {"intake"},
            "needs/0": {"transcript"},
            "needs/1": {"transcript"},
            "goals/0": {"transcript", "intake"},
            "goals/1": {"intake"},
        },
    },
    "transcript_only_unnamed": {
        "documents": {"transcript": UNNAMED_CALL},
        "draft": {
            "name": None,
            "needs": ["Invoices are sent late"],
            "goals": ["Automate invoicing by spring"],
            "source_references": [
                ("needs/0", "transcript", "Our invoices go out late every month."),
                ("goals/0", "transcript", "invoicing to be automated by spring"),
            ],
        },
        "expected": {"needs/0": {"transcript"}, "goals/0": {"transcript"}},
    },
}


def store_sources(db, stored_document, documents):
    """Store each document with its extracted text, as ingestion would."""
    sources = []
    for kind, text in documents.items():
        document = stored_document(data=text.encode(), filename=f"{kind}.txt")
        db.add(ExtractedText(document_id=document.id, text=text))
        sources.append(SourceInput(document_id=str(document.id), kind=kind, text=text))
    db.commit()
    return sources


def model_reply(draft, sources):
    """The fake model's JSON, citing the stored document ID for each kind."""
    ids = {source.kind: source.document_id for source in sources}
    references = [
        {"field": field, "document_id": ids[kind], "quote": quote}
        for field, kind, quote in draft["source_references"]
    ]
    return {**draft, "source_references": references}


def populated_fields(data):
    names = ["name"] if data["name"] is not None else []
    return {
        *names,
        *(f"needs/{index}" for index in range(len(data["needs"]))),
        *(f"goals/{index}" for index in range(len(data["goals"]))),
    }


@pytest.mark.parametrize("example", EXAMPLES.values(), ids=EXAMPLES.keys())
def test_every_saved_field_links_to_its_source_passage(
    client, db_session, profile_factory, stored_document, demo_client, example
):
    profile = profile_factory()
    sources = store_sources(db_session, stored_document, example["documents"])
    provider = FakeProvider(json.dumps(model_reply(example["draft"], sources)))

    draft = generate_source_profile(sources, provider)
    url = f"/client-profiles/{profile.client_profile_id}"
    response = client.post(f"{url}/source-drafts", json=draft.model_dump())
    assert response.status_code == 201
    saved = client.get(f"{url}/versions").json()[-1]["data"]
    assert saved == draft.model_dump()

    # Read the client's documents back from the database, not from the fixtures.
    stored = db_session.execute(
        select(SourceDocument.id, ExtractedText.text)
        .join(ExtractedText, ExtractedText.document_id == SourceDocument.id)
        .where(SourceDocument.client_id == demo_client.id)
    ).all()
    texts = {str(document_id): text for document_id, text in stored}
    kinds = {source.document_id: source.kind for source in sources}
    linked = {}
    for reference in saved["source_references"]:
        document_id, quote = reference["document_id"], reference["quote"]
        assert document_id in texts, "reference is not this client's document"
        assert quote in texts[document_id]
        # Controlled examples: the quote occurs in no other document, so the
        # link can only open the right one.
        assert [other for other in texts.values() if quote in other] == [
            texts[document_id]
        ]
        linked.setdefault(reference["field"], set()).add(kinds[document_id])
    assert populated_fields(saved) == set(example["expected"])
    assert linked == example["expected"]


def test_real_quote_cited_from_the_wrong_document_is_not_saved(
    client, db_session, profile_factory, stored_document
):
    profile = profile_factory()
    example = EXAMPLES["transcript_and_intake"]
    sources = store_sources(db_session, stored_document, example["documents"])
    payload = model_reply(example["draft"], sources)
    # "Contact name: Maya Chen" is real, but only the intake form contains it.
    payload["source_references"][0]["document_id"] = sources[0].document_id

    response = client.post(
        f"/client-profiles/{profile.client_profile_id}/source-drafts", json=payload
    )

    assert response.status_code == 422
    assert "occur exactly" in response.json()["detail"]
    count = select(func.count()).select_from(ClientProfileVersion)
    assert db_session.scalar(count) == 1
