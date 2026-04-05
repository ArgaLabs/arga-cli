from __future__ import annotations

import json
import sys

import pytest

from arga_cli import main

SAMPLE_SCENARIOS = [
    {
        "id": "sc_001",
        "name": "Billing edge cases",
        "twins": ["stripe"],
        "tags": ["billing", "edge"],
        "created_at": "2026-03-01T10:00:00Z",
    },
    {
        "id": "sc_002",
        "name": "Slack notifications",
        "twins": ["slack"],
        "tags": ["messaging"],
        "created_at": "2026-03-15T12:00:00Z",
    },
]

SAMPLE_SCENARIO_DETAIL = {
    "id": "sc_001",
    "name": "Billing edge cases",
    "description": "Tests for failed payments and refunds",
    "prompt": "Set up Stripe with a customer that has a failed payment",
    "twins": ["stripe"],
    "tags": ["billing", "edge"],
    "seed_config": {"customers": [{"name": "Test User"}], "charges": [{"amount": 1000}]},
    "created_at": "2026-03-01T10:00:00Z",
    "updated_at": "2026-03-02T14:00:00Z",
}


def test_scenarios_list_table_output(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.setattr(main, "load_api_key", lambda: "arga_api_key")
    monkeypatch.setattr(main.ApiClient, "close", lambda self: None)

    def fake_list(self, *, twin=None, tag=None):
        return SAMPLE_SCENARIOS

    monkeypatch.setattr(main.ApiClient, "list_scenarios", fake_list)

    exit_code = main.run_scenarios_cli(["list"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Billing edge cases" in output
    assert "Slack notifications" in output


def test_scenarios_list_json_output(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.setattr(main, "load_api_key", lambda: "arga_api_key")
    monkeypatch.setattr(main.ApiClient, "close", lambda self: None)

    def fake_list(self, *, twin=None, tag=None):
        return SAMPLE_SCENARIOS

    monkeypatch.setattr(main.ApiClient, "list_scenarios", fake_list)

    exit_code = main.run_scenarios_cli(["list", "--json"])
    output = capsys.readouterr().out

    assert exit_code == 0
    parsed = json.loads(output)
    assert len(parsed) == 2
    assert parsed[0]["name"] == "Billing edge cases"


def test_scenarios_list_empty(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.setattr(main, "load_api_key", lambda: "arga_api_key")
    monkeypatch.setattr(main.ApiClient, "close", lambda self: None)

    monkeypatch.setattr(main.ApiClient, "list_scenarios", lambda self, *, twin=None, tag=None: [])

    exit_code = main.run_scenarios_cli(["list"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "No scenarios found." in output


def test_scenarios_list_with_filters(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.setattr(main, "load_api_key", lambda: "arga_api_key")
    monkeypatch.setattr(main.ApiClient, "close", lambda self: None)

    captured_params: dict = {}

    def fake_list(self, *, twin=None, tag=None):
        captured_params["twin"] = twin
        captured_params["tag"] = tag
        return []

    monkeypatch.setattr(main.ApiClient, "list_scenarios", fake_list)

    main.run_scenarios_cli(["list", "--twin", "slack", "--tag", "billing"])

    assert captured_params["twin"] == "slack"
    assert captured_params["tag"] == "billing"


def test_scenarios_create_from_prompt(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.setattr(main, "load_api_key", lambda: "arga_api_key")
    monkeypatch.setattr(main.ApiClient, "close", lambda self: None)

    captured_payload: dict = {}

    def fake_create(self, *, name, description=None, prompt=None, seed_config=None, twins=None, tags=None):
        captured_payload.update(
            {"name": name, "description": description, "prompt": prompt, "twins": twins, "tags": tags}
        )
        return {"id": "sc_new", "name": name}

    monkeypatch.setattr(main.ApiClient, "create_scenario", fake_create)

    exit_code = main.run_scenarios_cli(
        ["create", "--name", "My Scenario", "--prompt", "Set up billing", "--tags", "billing,test"]
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Created scenario: My Scenario" in output
    assert "ID: sc_new" in output
    assert captured_payload["name"] == "My Scenario"
    assert captured_payload["prompt"] == "Set up billing"
    assert captured_payload["tags"] == ["billing", "test"]


def test_scenarios_create_json_output(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.setattr(main, "load_api_key", lambda: "arga_api_key")
    monkeypatch.setattr(main.ApiClient, "close", lambda self: None)

    def fake_create(self, *, name, description=None, prompt=None, seed_config=None, twins=None, tags=None):
        return {"id": "sc_new", "name": name}

    monkeypatch.setattr(main.ApiClient, "create_scenario", fake_create)

    exit_code = main.run_scenarios_cli(["create", "--name", "My Scenario", "--json"])
    output = capsys.readouterr().out

    assert exit_code == 0
    parsed = json.loads(output)
    assert parsed["id"] == "sc_new"


def test_scenarios_show_detail(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.setattr(main, "load_api_key", lambda: "arga_api_key")
    monkeypatch.setattr(main.ApiClient, "close", lambda self: None)

    def fake_get(self, scenario_id):
        assert scenario_id == "sc_001"
        return SAMPLE_SCENARIO_DETAIL

    monkeypatch.setattr(main.ApiClient, "get_scenario", fake_get)

    exit_code = main.run_scenarios_cli(["show", "sc_001"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Billing edge cases" in output


def test_scenarios_show_json(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.setattr(main, "load_api_key", lambda: "arga_api_key")
    monkeypatch.setattr(main.ApiClient, "close", lambda self: None)

    def fake_get(self, scenario_id):
        return SAMPLE_SCENARIO_DETAIL

    monkeypatch.setattr(main.ApiClient, "get_scenario", fake_get)

    exit_code = main.run_scenarios_cli(["show", "sc_001", "--json"])
    output = capsys.readouterr().out

    assert exit_code == 0
    parsed = json.loads(output)
    assert parsed["id"] == "sc_001"
    assert parsed["prompt"] == "Set up Stripe with a customer that has a failed payment"


def test_scenarios_update(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.setattr(main, "load_api_key", lambda: "arga_api_key")
    monkeypatch.setattr(main.ApiClient, "close", lambda self: None)

    captured_kwargs: dict = {}

    def fake_update(self, scenario_id, **kwargs):
        captured_kwargs.update(kwargs)
        return {"id": scenario_id, "name": kwargs.get("name", "Updated")}

    monkeypatch.setattr(main.ApiClient, "update_scenario", fake_update)

    exit_code = main.run_scenarios_cli(["update", "sc_001", "--name", "New Name", "--tags", "a,b"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Updated scenario" in output
    assert captured_kwargs["name"] == "New Name"
    assert captured_kwargs["tags"] == ["a", "b"]


def test_scenarios_update_no_fields_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "load_api_key", lambda: "arga_api_key")
    monkeypatch.setattr(main.ApiClient, "close", lambda self: None)

    with pytest.raises(main.CliError, match="No fields to update"):
        main.run_scenarios_cli(["update", "sc_001"])


def test_scenarios_delete(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.setattr(main, "load_api_key", lambda: "arga_api_key")
    monkeypatch.setattr(main.ApiClient, "close", lambda self: None)

    deleted_id: list[str] = []

    def fake_delete(self, scenario_id):
        deleted_id.append(scenario_id)
        return {}

    monkeypatch.setattr(main.ApiClient, "delete_scenario", fake_delete)

    # Mock questionary to auto-confirm
    import questionary

    monkeypatch.setattr(questionary, "confirm", lambda *a, **kw: type("Q", (), {"ask": lambda self: True})())

    exit_code = main.run_scenarios_cli(["delete", "sc_001"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Deleted scenario sc_001" in output
    assert deleted_id == ["sc_001"]


def test_scenarios_delete_cancelled(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.setattr(main, "load_api_key", lambda: "arga_api_key")
    monkeypatch.setattr(main.ApiClient, "close", lambda self: None)

    import questionary

    monkeypatch.setattr(questionary, "confirm", lambda *a, **kw: type("Q", (), {"ask": lambda self: False})())

    exit_code = main.run_scenarios_cli(["delete", "sc_001"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Cancelled" in output


def test_main_dispatches_scenarios_before_argparse(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_scenarios_cli(argv: list[str]) -> int:
        captured["argv"] = argv
        return 0

    monkeypatch.setattr(main, "run_scenarios_cli", fake_scenarios_cli)
    monkeypatch.setattr(sys, "argv", ["arga", "scenarios", "list", "--json"])

    with pytest.raises(SystemExit) as exc_info:
        main.main()

    assert exc_info.value.code == 0
    assert captured["argv"] == ["list", "--json"]


def test_scenarios_help(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    exit_code = main.run_scenarios_cli([])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "arga scenarios" in output
    assert "list" in output
    assert "create" in output
    assert "show" in output
    assert "update" in output
    assert "delete" in output
