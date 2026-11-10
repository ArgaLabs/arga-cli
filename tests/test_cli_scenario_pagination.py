import json

import httpx
import pytest

from arga_cli import main


@pytest.mark.parametrize("json_output", [False, True])
def test_command_lists_every_page_and_preserves_filters(monkeypatch, capsys, json_output):
    rows = [
        {"id": f"scenario-{index}", "name": f"Scenario {index}", "twins": ["slack"], "tags": []} for index in range(121)
    ]
    requests = []

    def respond(request):
        requests.append(request)
        assert request.headers["Authorization"] == "Bearer test-key"
        assert request.url.params["include_presets"] == "true"
        assert request.url.params["twin"] == "slack"
        assert request.url.params["tag"] == "support"
        assert request.url.params["limit"] == "100"
        offset = int(request.url.params["offset"])
        return httpx.Response(200, json=rows[offset : offset + 100], headers={"X-Pagination-Limit": "100"})

    client = main.ApiClient("https://api.example.test", api_key="test-key")
    client._client.close()
    client._client = httpx.Client(transport=httpx.MockTransport(respond))
    monkeypatch.setattr(main, "load_api_key", lambda: "test-key")
    monkeypatch.setattr(main, "ApiClient", lambda *_args, **_kwargs: client)
    flags = ["--json"] if json_output else []
    args = main.build_parser().parse_args(
        ["test-runner", "scenarios", "list", "--include-presets", "--twin", "slack", "--tag", "support", *flags]
    )
    assert args.func(args) == 0
    output = capsys.readouterr().out
    if json_output:
        assert json.loads(output) == rows
    else:
        assert all(f"Scenario {index}" in output for index in range(121))
    assert [request.url.params["offset"] for request in requests] == ["0", "100"]


@pytest.mark.parametrize("count", [0, 100, 200])
def test_empty_and_exact_page_boundaries(count):
    rows = [{"id": str(index)} for index in range(count)]
    offsets = []

    def respond(request):
        offset = int(request.url.params["offset"])
        offsets.append(offset)
        return httpx.Response(200, json=rows[offset : offset + 100], headers={"X-Pagination-Limit": "100"})

    client = main.ApiClient("https://api.example.test", api_key="test-key")
    client._client.close()
    client._client = httpx.Client(transport=httpx.MockTransport(respond))
    try:
        assert client.list_scenarios() == rows
        assert offsets == list(range(0, count + 1, 100))
    finally:
        client.close()


@pytest.mark.parametrize("count", [50, 100, 121])
def test_client_can_ship_before_api_pagination(count):
    rows = [{"id": str(index)} for index in range(count)]
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(200, json=rows)  # Legacy server ignores limit/offset.

    client = main.ApiClient("https://api.example.test", api_key="test-key")
    client._client.close()
    client._client = httpx.Client(transport=httpx.MockTransport(respond))
    try:
        assert client.list_scenarios() == rows
        assert len(calls) == 1
    finally:
        client.close()


def test_second_page_failure_does_not_return_a_silently_truncated_list():
    def respond(request):
        if request.url.params["offset"] == "0":
            return httpx.Response(200, json=[{"id": str(i)} for i in range(100)], headers={"X-Pagination-Limit": "100"})
        return httpx.Response(503, json={"detail": "Temporarily unavailable"})

    client = main.ApiClient("https://api.example.test", api_key="test-key")
    client._client.close()
    client._client = httpx.Client(transport=httpx.MockTransport(respond))
    try:
        with pytest.raises(main.CliError, match="Temporarily unavailable"):
            client.list_scenarios()
    finally:
        client.close()
