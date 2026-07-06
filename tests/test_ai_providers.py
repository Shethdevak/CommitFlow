import pytest
from app.ai.openai_provider import OpenAIProvider
from app.ai.gemini_provider import GeminiProvider
from app.ai.anthropic_provider import AnthropicProvider
from app.ai.openrouter_provider import OpenRouterProvider
from app.ai.ollama_provider import OllamaProvider

def test_openai_provider(mocker):
    """Tests that OpenAIProvider builds the correct request and returns the choices content."""
    mock_response = mocker.Mock()
    mock_response.json.return_value = {
        "choices": [
            {"message": {"content": '{"selected_features": []}'}}
        ]
    }
    mock_post = mocker.patch("requests.post", return_value=mock_response)

    provider = OpenAIProvider(api_key="sk-test", model="gpt-4o")
    result = provider.classify("test prompt")

    assert result == '{"selected_features": []}'
    mock_post.assert_called_once()
    # verify Authorization headers
    headers = mock_post.call_args[1]["headers"]
    assert headers["Authorization"] == "Bearer sk-test"


def test_gemini_provider(mocker):
    """Tests that GeminiProvider maps response structures and appends API key in URL params."""
    mock_response = mocker.Mock()
    mock_response.json.return_value = {
        "candidates": [
            {"content": {"parts": [{"text": '{"gemini": true}'}]}}
        ]
    }
    mock_post = mocker.patch("requests.post", return_value=mock_response)

    provider = GeminiProvider(api_key="gemini-key", model="gemini-1.5-flash")
    result = provider.classify("test prompt")

    assert result == '{"gemini": true}'
    url_called = mock_post.call_args[0][0]
    assert "key=gemini-key" in url_called
    assert "gemini-1.5-flash" in url_called


def test_anthropic_provider(mocker):
    """Tests that AnthropicProvider formats the messages payloads and passes custom headers."""
    mock_response = mocker.Mock()
    mock_response.json.return_value = {
        "content": [
            {"text": '{"anthropic": true}'}
        ]
    }
    mock_post = mocker.patch("requests.post", return_value=mock_response)

    provider = AnthropicProvider(api_key="anthropic-key", model="claude-3-5-sonnet")
    result = provider.classify("test prompt")

    assert result == '{"anthropic": true}'
    headers = mock_post.call_args[1]["headers"]
    assert headers["x-api-key"] == "anthropic-key"
    assert headers["anthropic-version"] == "2023-06-01"


def test_openrouter_provider(mocker):
    """Tests that OpenRouterProvider sends title and HTTP-Referer headers."""
    mock_response = mocker.Mock()
    mock_response.json.return_value = {
        "choices": [
            {"message": {"content": '{"openrouter": true}'}}
        ]
    }
    mock_post = mocker.patch("requests.post", return_value=mock_response)

    provider = OpenRouterProvider(api_key="or-key", model="llama-3")
    result = provider.classify("test prompt")

    assert result == '{"openrouter": true}'
    headers = mock_post.call_args[1]["headers"]
    assert headers["Authorization"] == "Bearer or-key"
    assert "HTTP-Referer" in headers


def test_ollama_provider(mocker):
    """Tests that OllamaProvider executes locally against base URL and forces json output format."""
    mock_response = mocker.Mock()
    mock_response.json.return_value = {
        "message": {"content": '{"ollama": true}'}
    }
    mock_post = mocker.patch("requests.post", return_value=mock_response)

    provider = OllamaProvider(base_url="http://127.0.0.1:11434", model="llama3")
    result = provider.classify("test prompt")

    assert result == '{"ollama": true}'
    # Check that format=json was passed
    json_body = mock_post.call_args[1]["json"]
    assert json_body["format"] == "json"
    assert json_body["model"] == "llama3"
