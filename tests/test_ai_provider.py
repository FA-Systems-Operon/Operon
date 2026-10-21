"""Provider adapter tests. Ollama is faked with httpx.MockTransport; CI has no model."""

import json

import httpx
import pytest

from src.ai import (
    ProviderConfigError,
    ProviderError,
    ProviderResponseError,
    ProviderTimeout,
    ProviderUnavailable,
    get_provider,
)
from src.ai.ollama import OllamaProvider
from src.config import settings


def make_provider(handler):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return OllamaProvider(base_url="http://x", model="m", client=client)


def test_generate_returns_model_response():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"response": "hi"})

    result = make_provider(handler).generate("Say hi", system="Be brief.")

    assert result.text == "hi"
    assert result.provider == "ollama"
    assert result.model == "m"
    assert result.duration_ms >= 0
    assert str(requests[0].url) == "http://x/api/generate"
    body = json.loads(requests[0].content)
    assert body["model"] == "m"
    assert body["prompt"] == "Say hi"
    assert body["system"] == "Be brief."
    assert body["stream"] is False
    assert body["options"] == {"temperature": 0, "seed": 42}
    assert "format" not in body


def test_json_output_adds_format():
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"response": "{}"})

    make_provider(handler).generate("Give JSON", json_output=True)

    assert bodies[0]["format"] == "json"


def test_error_status_raises_response_error():
    provider = make_provider(lambda request: httpx.Response(500, text="boom"))

    with pytest.raises(ProviderResponseError):
        provider.generate("Say hi")


def test_missing_response_key_raises_response_error():
    provider = make_provider(lambda request: httpx.Response(200, json={"done": True}))

    with pytest.raises(ProviderResponseError):
        provider.generate("Say hi")


@pytest.mark.parametrize("value", [None, 42, ["hi"], {"text": "hi"}])
def test_non_string_response_raises_response_error(value):
    provider = make_provider(
        lambda request: httpx.Response(200, json={"response": value})
    )

    with pytest.raises(ProviderResponseError, match="not a string"):
        provider.generate("Say hi")


def test_timeout_raises_provider_timeout():
    def handler(request):
        raise httpx.ReadTimeout("too slow", request=request)

    with pytest.raises(ProviderTimeout):
        make_provider(handler).generate("Say hi")


def test_connection_failure_raises_provider_unavailable():
    def handler(request):
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(ProviderUnavailable):
        make_provider(handler).generate("Say hi")


def test_provider_errors_share_a_base_class():
    for error in (ProviderUnavailable, ProviderTimeout, ProviderResponseError):
        assert issubclass(error, ProviderError)


def test_get_provider_builds_ollama_from_settings(monkeypatch):
    monkeypatch.setattr(settings, "AI_PROVIDER", "ollama")
    monkeypatch.setattr(settings, "OLLAMA_BASE_URL", "http://ollama:11434")
    monkeypatch.setattr(settings, "OLLAMA_MODEL", "llama3.2:3b")
    monkeypatch.setattr(settings, "OLLAMA_TIMEOUT_SECONDS", 30.0)

    provider = get_provider()

    assert isinstance(provider, OllamaProvider)
    assert provider.base_url == "http://ollama:11434"
    assert provider.model == "llama3.2:3b"
    assert provider.timeout == 30.0


def test_get_provider_rejects_unknown_provider(monkeypatch):
    monkeypatch.setattr(settings, "AI_PROVIDER", "nope")
    monkeypatch.setattr(settings, "OLLAMA_MODEL", "m")

    with pytest.raises(ProviderConfigError, match="Unknown AI_PROVIDER"):
        get_provider()


def test_get_provider_requires_model(monkeypatch):
    monkeypatch.setattr(settings, "AI_PROVIDER", "ollama")
    monkeypatch.setattr(settings, "OLLAMA_MODEL", "")

    with pytest.raises(ProviderConfigError, match="OLLAMA_MODEL"):
        get_provider()


def test_error_status_keeps_status_code_and_body():
    provider = make_provider(lambda request: httpx.Response(404, text="no model"))

    with pytest.raises(ProviderResponseError) as caught:
        provider.generate("Say hi")

    assert caught.value.status_code == 404
    assert caught.value.body == "no model"


def test_non_json_reply_raises_response_error():
    provider = make_provider(lambda request: httpx.Response(200, text="not json"))

    with pytest.raises(ProviderResponseError):
        provider.generate("Say hi")


def test_list_models_returns_names():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"models": [{"name": "a"}, {"name": "b"}]})

    assert make_provider(handler).list_models(timeout=3) == ["a", "b"]
    assert requests[0].method == "GET"
    assert str(requests[0].url) == "http://x/api/tags"


def test_list_models_maps_connection_failure():
    def handler(request):
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(ProviderUnavailable):
        make_provider(handler).list_models()


@pytest.mark.parametrize("body", [[], {"models": [{"id": "a"}]}, {"models": [3]}])
def test_list_models_rejects_unexpected_shape(body):
    provider = make_provider(lambda request: httpx.Response(200, json=body))

    with pytest.raises(ProviderResponseError, match="unexpected model list"):
        provider.list_models()


def test_other_transport_error_raises_provider_unavailable():
    def handler(request):
        raise httpx.RemoteProtocolError("dropped", request=request)

    with pytest.raises(ProviderUnavailable, match="RemoteProtocolError"):
        make_provider(handler).generate("Say hi")
