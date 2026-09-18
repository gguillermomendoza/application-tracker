from unittest.mock import patch

from src import extraction


def test_vertex_client_is_configured_with_retry_options(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "global")

    with patch("src.extraction.genai.Client") as mock_client:
        extraction.get_vertex_client()

    mock_client.assert_called_once()

    kwargs = mock_client.call_args.kwargs

    assert kwargs["vertexai"] is True
    assert kwargs["project"] == "test-project"
    assert kwargs["location"] == "global"

    http_options = kwargs["http_options"]
    retry_options = http_options.retry_options

    assert http_options.api_version == "v1"
    assert retry_options.attempts == 5
    assert retry_options.initial_delay == 1.0
    assert retry_options.max_delay == 30.0
    assert retry_options.exp_base == 2.0
    assert retry_options.jitter == 1.0
    assert retry_options.http_status_codes == [429, 500, 502, 503, 504]
