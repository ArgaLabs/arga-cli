import json
import uuid

import httpx
import pytest

from arga_cli import fidelity, main


@pytest.fixture
def client(monkeypatch):
    calls = []

    class Client:
        def __init__(self, *_args, **_kwargs):
            pass

        def close(self):
            calls.append("closed")

        def fidelity_request(self, method, path, payload=None, *, invocation_headers):
            calls.append((method, path, payload, invocation_headers))
            return {"id": "id", "connector": "linear", "status": "submitted"}

    monkeypatch.setattr(main, "ApiClient", Client)
    monkeypatch.setattr(main, "load_api_key", lambda: "test-key")
    return calls


def test_submit_preserves_markdown_and_stable_retry_key(client, tmp_path, capsys):
    report = tmp_path / "report.md"
    report.write_text("# G1\nUnicode: 日本語\n")
    args = main.build_parser().parse_args(["fidelity-gaps", "submit", str(report), "--connector", "linear", "--json"])
    assert args.func(args) == 0
    assert args.func(args) == 0
    first, second = client[0][2], client[2][2]
    assert first == second
    assert first["markdown"] == report.read_text()
    assert len(first["idempotency_key"]) == 64
    first_headers, second_headers = client[0][3], client[2][3]
    assert first_headers["X-Arga-CLI-Command"] == second_headers["X-Arga-CLI-Command"] == "submit"
    assert uuid.UUID(first_headers["X-Arga-CLI-Invocation-ID"]).version == 4
    assert first_headers["X-Arga-CLI-Invocation-ID"] != second_headers["X-Arga-CLI-Invocation-ID"]
    assert "test-key" not in capsys.readouterr().out


@pytest.mark.parametrize("value", ["nan", "inf", "0", "-1"])
def test_polling_rejects_nonfinite_or_nonpositive_intervals(value):
    with pytest.raises(SystemExit):
        main.build_parser().parse_args(["fidelity-gaps", "wait", str(uuid.uuid4()), "--poll-interval", value])


def test_failed_wait_outputs_structured_state_and_returns_nonzero(monkeypatch, capsys):
    class Client:
        def __init__(self, *_args, **_kwargs):
            pass

        def close(self):
            pass

        def fidelity_request(self, *_args, **_kwargs):
            return {
                "id": "id",
                "connector": "linear",
                "status": "needs_information",
                "milestones": {"submitted": "time"},
            }

    monkeypatch.setattr(main, "ApiClient", Client)
    monkeypatch.setattr(main, "load_api_key", lambda: "test")
    args = main.build_parser().parse_args(["fidelity-gaps", "wait", str(uuid.uuid4()), "--json"])
    assert args.func(args) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "needs_information"


def test_wait_reached_milestone_survives_later_customer_failure(monkeypatch):
    class Client:
        def __init__(self, *_args, **_kwargs):
            pass

        def close(self):
            pass

        def fidelity_request(self, *_args, **_kwargs):
            return {
                "id": "id",
                "connector": "linear",
                "status": "customer_rejected",
                "milestones": {"deployed": "time"},
            }

    monkeypatch.setattr(main, "ApiClient", Client)
    monkeypatch.setattr(main, "load_api_key", lambda: "test")
    args = main.build_parser().parse_args(["fidelity-gaps", "wait", str(uuid.uuid4()), "--json"])
    assert args.func(args) == 0


def test_invalid_file_is_rejected_before_upload(client, tmp_path):
    report = tmp_path / "report.md"
    report.write_bytes(b"\xff")
    args = main.build_parser().parse_args(["fidelity-gaps", "submit", str(report), "--connector", "linear"])
    with pytest.raises(main.CliError, match="UTF-8"):
        args.func(args)
    assert client == ["closed"]


def test_wait_recovers_transient_failures_and_honors_short_interval_without_hint(monkeypatch, capsys):
    clock = {"now": 0.0}
    sleeps, timeouts = [], []
    headers = []
    states = [
        main.RetryableApiError("temporary"),
        httpx.ConnectError("temporary"),
        {"id": "id", "connector": "linear", "status": "deployed"},
    ]

    class Client:
        def __init__(self, *_args, **_kwargs):
            pass

        def close(self):
            pass

        def fidelity_request(self, *_args, timeout=None, invocation_headers):
            timeouts.append(timeout)
            headers.append(invocation_headers)
            item = states.pop(0)
            if isinstance(item, Exception):
                raise item
            return item

    def sleep(seconds):
        sleeps.append(seconds)
        clock["now"] += seconds

    monkeypatch.setattr(main, "ApiClient", Client)
    monkeypatch.setattr(main, "load_api_key", lambda: "fixture")
    monkeypatch.setattr(fidelity.time, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(fidelity.time, "sleep", sleep)
    args = main.build_parser().parse_args(
        ["fidelity-gaps", "wait", str(uuid.uuid4()), "--poll-interval", "0.25", "--timeout", "2", "--json"]
    )
    assert args.func(args) == 0
    assert sleeps == [0.25, 0.25]
    assert all(timeout <= 2 for timeout in timeouts)
    assert headers == [headers[0]] * 3
    assert headers[0]["X-Arga-CLI-Command"] == "wait"
    assert json.loads(capsys.readouterr().out)["status"] == "deployed"


def test_wait_exhaustion_is_local_timeout_with_unknown_remote_state(monkeypatch, capsys):
    clock = {"now": 0.0}

    class Client:
        def __init__(self, *_args, **_kwargs):
            pass

        def close(self):
            pass

        def fidelity_request(self, *_args, **_kwargs):
            raise main.RetryableApiError("temporary", retry_after=10)

    monkeypatch.setattr(main, "ApiClient", Client)
    monkeypatch.setattr(main, "load_api_key", lambda: "fixture")
    monkeypatch.setattr(fidelity.time, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(fidelity.time, "sleep", lambda seconds: clock.update(now=clock["now"] + seconds))
    args = main.build_parser().parse_args(["fidelity-gaps", "wait", str(uuid.uuid4()), "--timeout", "2", "--json"])
    assert args.func(args) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["poll_status"] == "timed_out" and result["status"] == "unknown"
    assert clock["now"] == 2


def test_status_alias_sends_get_invocation_headers(monkeypatch, capsys):
    requests = []

    def response(request):
        requests.append(request)
        return httpx.Response(200, json={"id": "report", "status": "deployed"})

    monkeypatch.setattr(main, "load_api_key", lambda: "fixture")
    client = main.ApiClient("https://api.test", "fixture")
    client._client.close()
    client._client = httpx.Client(transport=httpx.MockTransport(response))
    monkeypatch.setattr(main, "ApiClient", lambda *_args, **_kwargs: client)
    args = main.build_parser().parse_args(["fidelity-gaps", "status", str(uuid.uuid4()), "--json"])

    assert args.func(args) == 0
    assert requests[0].headers["X-Arga-CLI-Command"] == "get"
    assert uuid.UUID(requests[0].headers["X-Arga-CLI-Invocation-ID"]).version == 4
    assert requests[0].headers["Authorization"] == "Bearer fixture"
    assert json.loads(capsys.readouterr().out)["status"] == "deployed"


@pytest.mark.parametrize("status", [429, 500, 503])
def test_api_marks_retryable_responses_and_preserves_retry_after(status):
    client = main.ApiClient("https://api.test", "fixture")
    client._client.close()
    client._client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(status, json={"detail": "unavailable"}, headers={"Retry-After": "3"})
        )
    )
    try:
        with pytest.raises(main.RetryableApiError) as error:
            client.fidelity_request("GET", "/id", timeout=1)
        assert error.value.retry_after == 3
        assert "unavailable" in str(error.value)
        assert "idempotency key" not in str(error.value)
    finally:
        client.close()
