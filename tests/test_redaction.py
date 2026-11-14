"""M14: no email or phone number reaches a model.

The fake Ollama server records every request body, and the tests check that
body, the bytes that would actually leave the app, for emails and phones.
"""

import json

import httpx
import pytest

from src.ai.ollama import OllamaProvider
from src.ai.provider import get_provider
from src.ai.redaction import RedactingProvider, redact, restore
from src.config import settings

EMAILS = [
    "anna.client@example.com",
    "billing+invoices@acme-corp.ca",
    "J.Doe@sub.mail.co.uk",
]
PHONES = [
    "(514) 555-1234",
    "514-555-9876",
    "514.555.0000",
    "514 555 4321",
    "1-800-555-0199",
    "+1 438 555 7788",
    "+44 20 7946 0958",
    "+15145550123",
    "613-555-0100 ext. 22",
]

SOURCE = (
    "Intake form\n"
    f"Main contact: {EMAILS[0]}, invoices go to {EMAILS[1]}.\n"
    f"Ops lead: {EMAILS[2]}\n"
    f"Phones: {', '.join(PHONES)}\n"
    "NEQ: 1171234567\n"
)


def recording_provider(reply: str = "ok"):
    sent: list[dict] = []

    def handler(request):
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"response": reply})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    inner = OllamaProvider(base_url="http://x", model="m", client=client)
    return RedactingProvider(inner), sent


def assert_no_pii(payload: str):
    for value in EMAILS + PHONES:
        assert value not in payload, f"{value!r} reached the model"
    assert "@" not in payload


def test_no_email_or_phone_reaches_the_model():
    provider, sent = recording_provider()

    provider.generate(SOURCE, system=f"Reply to {EMAILS[0]} or {PHONES[0]}.")

    assert len(sent) == 1
    assert_no_pii(json.dumps(sent[0]))
    assert "[EMAIL_1]" in sent[0]["prompt"]
    assert "[PHONE_1]" in sent[0]["prompt"]


def test_get_provider_redacts_every_call(monkeypatch):
    """The real factory, which every caller in the app uses, must redact."""
    sent: list[dict] = []

    def handler(request):
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"response": "ok"})

    monkeypatch.setattr(settings, "AI_PROVIDER", "ollama")
    monkeypatch.setattr(settings, "OLLAMA_MODEL", "m")
    monkeypatch.setattr(
        "src.ai.ollama._default_client",
        httpx.Client(transport=httpx.MockTransport(handler)),
    )

    get_provider().generate(SOURCE, json_output=True)

    assert_no_pii(json.dumps(sent[0]))


def test_reply_gets_real_values_back():
    """Extraction still works: the model answers with tokens, callers get values."""
    reply = json.dumps({"email": "[EMAIL_1]", "phone_number": "[PHONE_1]"})
    provider, _ = recording_provider(reply)

    result = json.loads(provider.generate(SOURCE).text)

    assert result == {"email": EMAILS[0], "phone_number": PHONES[0]}


def test_same_value_gets_same_token():
    text, tokens = redact(f"{EMAILS[0]} and again {EMAILS[0]}")

    assert text == "[EMAIL_1] and again [EMAIL_1]"
    assert tokens == {"[EMAIL_1]": EMAILS[0]}


@pytest.mark.parametrize(
    "keep",
    [
        "NEQ 1171234567",  # 10-digit business number, no separators
        "CRA BN 123456789RT0001",
        "Invoice 2024-11-09",
        "Version 1.2.3",
        "Price $1,250.00",
        "Postal code H2X 1Y4",
    ],
)
def test_non_contact_numbers_are_left_alone(keep):
    text, tokens = redact(keep)

    assert text == keep
    assert tokens == {}


def test_restore_ignores_unknown_tokens():
    assert (
        restore("[PHONE_9] stays", {"[PHONE_1]": "514-555-1234"}) == "[PHONE_9] stays"
    )


@pytest.mark.parametrize("escape", [r"\n", r"\r", r"\t"])
@pytest.mark.parametrize("phone", ["514-555-1234", "(514) 555-1234", "+1 438 555 7788"])
def test_phone_after_escaped_whitespace_is_redacted(escape, phone):
    """Text that was JSON-encoded holds a literal backslash-n, not a newline.

    The "n" in that escape is a word character, so it must not stop a phone
    right after it from being redacted.
    """
    text, tokens = redact(f"Phone:{escape}{phone}{escape}Next line")

    assert text == f"Phone:{escape}[PHONE_1]{escape}Next line"
    assert tokens == {"[PHONE_1]": phone}


def test_escaped_newline_reaches_the_model_redacted():
    provider, sent = recording_provider()

    provider.generate(json.dumps({"notes": "Call\n514-555-1234\nor email"}))

    assert "514-555-1234" not in json.dumps(sent[0])


SPLIT_PHONES = [
    "(514)\n555-1234",  # line break after the area code
    "613-555-0100\next. 22",  # line break before the extension
    "(438)\r\n555-7788",  # Windows line ending
    "514-555-1234\r\next. 5",  # Windows line ending before the extension
]


@pytest.mark.parametrize("phone", SPLIT_PHONES)
def test_json_reply_stays_valid_when_phone_has_line_break(phone):
    """A phone split over two lines is put back escaped, so the JSON still parses.

    The parsed value keeps the line break, so it still matches the source text.
    """
    reply = json.dumps({"phone_number": "[PHONE_1]"})
    provider, sent = recording_provider(reply)

    response = provider.generate(f"Phone: {phone}", json_output=True)

    assert sent[0]["prompt"] == "Phone: [PHONE_1]"
    assert json.loads(response.text) == {"phone_number": phone}


def test_json_reply_with_output_schema_is_escaped_too():
    reply = json.dumps({"phone_number": "[PHONE_1]"})
    provider, _ = recording_provider(reply)

    response = provider.generate(
        f"Phone: {SPLIT_PHONES[0]}", output_schema={"type": "object"}
    )

    assert json.loads(response.text) == {"phone_number": SPLIT_PHONES[0]}


def test_plain_text_reply_gets_the_line_break_back_as_is():
    provider, _ = recording_provider("Call [PHONE_1] today.")

    response = provider.generate(f"Phone: {SPLIT_PHONES[0]}")

    assert response.text == f"Call {SPLIT_PHONES[0]} today."


@pytest.mark.parametrize(
    "phone",
    [
        r"(514)\n555-1234",  # escaped line break after the area code
        r"(438)\r\n555-7788",  # escaped Windows line ending
        r"613-555-0100\next. 22",  # escaped line break before the extension
        r"(514)\\n555-1234",  # escaped twice, e.g. a reply quoted in a prompt
    ],
)
def test_phone_with_escaped_line_break_inside_is_redacted(phone):
    text, tokens = redact(f"Phone: {phone} end")

    assert text == "Phone: [PHONE_1] end"
    assert tokens == {"[PHONE_1]": phone}


@pytest.mark.parametrize("phone", SPLIT_PHONES)
def test_json_encoded_document_with_split_phone_round_trips(phone):
    """Documents reach the model JSON-encoded, as source_prompt.py sends them.

    The number must not reach the model, and the parsed reply must hold the
    real line break so the value still matches the document text.
    """
    prompt = json.dumps([{"document_id": "D1", "text": f"Phone: {phone}"}])
    reply = json.dumps({"phone_number": "[PHONE_1]"})
    provider, sent = recording_provider(reply)

    response = provider.generate(prompt, json_output=True)

    assert "555" not in sent[0]["prompt"]
    assert json.loads(response.text) == {"phone_number": phone}
