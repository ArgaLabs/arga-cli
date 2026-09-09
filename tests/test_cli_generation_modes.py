from __future__ import annotations

import json

import httpx
import pytest

from arga_cli import main


@pytest.fixture
def requests(monkeypatch):
    captured = []
    original_init = main.ApiClient.__init__

    def respond(request):
        captured.append(request)
        return httpx.Response(200, json={"id": "scenario-1", "name": "Example", "run_id": "run-1"})

    def init(client, *args, **kwargs):
        original_init(client, *args, **kwargs)
        client._client.close()
        client._client = httpx.Client(transport=httpx.MockTransport(respond))

    monkeypatch.setattr(main.ApiClient, "__init__", init)
    monkeypatch.setattr(main, "load_api_key", lambda: "arga_test")
    monkeypatch.setattr(main, "_resolve_ttl", lambda client, ttl: 60)
    return captured


@pytest.mark.parametrize("mode", [None, "fast", "thorough"])
@pytest.mark.parametrize("prefix", [["scenarios"], ["test-runner", "scenarios"]])
def test_scenario_create_serializes_generation_mode(requests, mode, prefix):
    argv = [*prefix, "create", "--name", "Example", "--prompt", "A Slack support channel", "--json"]
    if mode:
        argv += ["--generation-mode", mode]
    args = main.build_parser().parse_args(argv)
    assert args.func(args) == 0
    assert requests[0].url.path == "/scenarios"
    expected = {"name": "Example", "prompt": "A Slack support channel"}
    if mode:
        expected["generation_mode"] = mode
    assert json.loads(requests[0].content) == expected


@pytest.mark.parametrize("mode", [None, "fast", "thorough"])
@pytest.mark.parametrize("prefix", [["twin-runs", "create"], ["previews", "twins", "provision"]])
def test_twin_run_serializes_generation_mode(requests, mode, prefix):
    argv = [*prefix, "--twins", "slack", "--scenario-prompt", "A support channel", "--json"]
    if mode:
        argv += ["--generation-mode", mode]
    args = main.build_parser().parse_args(argv)
    assert args.func(args) == 0
    assert requests[0].url.path == "/twin-runs"
    body = json.loads(requests[0].content)
    assert body["scenario_prompt"] == "A support channel"
    if mode:
        assert body["scenario_generation_mode"] == mode
    else:
        assert "scenario_generation_mode" not in body
    assert "generation_mode" not in body


@pytest.mark.parametrize("operation", ["import", "update"])
@pytest.mark.parametrize("override", [None, "fast"])
def test_json_mode_is_preserved_or_overridden(requests, tmp_path, operation, override):
    payload = {"name": "Example", "prompt": "A support channel", "generation_mode": "thorough"}
    path = tmp_path / "scenario.json"
    path.write_text(json.dumps(payload))
    argv = ["scenarios", operation]
    if operation == "update":
        argv += ["scenario-1"]
    argv += ["--file", str(path), "--json"]
    if override:
        argv += ["--generation-mode", override]
    args = main.build_parser().parse_args(argv)
    assert args.func(args) == 0
    assert requests[0].method == ("PUT" if operation == "update" else "POST")
    assert json.loads(requests[0].content) == {**payload, "generation_mode": override or "thorough"}


@pytest.mark.parametrize(
    "argv",
    [
        ["scenarios", "create", "--name", "Example", "--prompt", "A channel"],
        ["twin-runs", "create", "--twins", "slack"],
    ],
)
def test_invalid_mode_is_rejected_before_request(requests, argv):
    with pytest.raises(SystemExit) as exc:
        main.build_parser().parse_args([*argv, "--generation-mode", "unknown"])
    assert exc.value.code == 2
    assert not requests
