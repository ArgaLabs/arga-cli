import json
import uuid

import pytest

from arga_cli import main


@pytest.fixture
def client(monkeypatch):
    calls = []

    class Client:
        def __init__(self, *_args, **_kwargs):
            pass

        def close(self):
            calls.append("closed")

        def fidelity_request(self, method, path, payload=None):
            calls.append((method, path, payload))
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

        def fidelity_request(self, *_args):
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

        def fidelity_request(self, *_args):
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
